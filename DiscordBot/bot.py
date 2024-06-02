# bot.py
from enum import Enum, auto
import discord
from discord.ext import commands
import os
import json
import logging
import re
import requests
from report import *
import pdb

# For Gemini automated moderation
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'tokens.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']


class ReportQueue:
    def __init__(self):
        self.high_queue = []
        self.med_queue = []
        self.low_queue = []

    def assign_priority(self, item):
        if item.threat_type is not None:
            item.priority = 'high'
        elif item.extremist_type == ExtremistContentType.PROPAGANDA or item.extremist_type == ExtremistContentType.VIOLENCE:
            item.priority = 'med'
        else:
            item.priority = 'low'

    def add(self, item):
        self.assign_priority(item)

        if item.priority == 'high':
            self.high_queue.append(item)
        elif item.priority == 'med':
            self.med_queue.append(item)
        elif item.priority == 'low':
            self.low_queue.append(item)

    def pop(self):
        if len(self.high_queue) > 0:
            return self.high_queue.pop(0)
        elif len(self.med_queue) > 0:
            return self.med_queue.pop(0)
        elif len(self.low_queue) > 0:
            return self.low_queue.pop(0)
        
        return None

    def peek(self):
        if len(self.high_queue) > 0:
            return self.high_queue[0]
        elif len(self.med_queue) > 0:
            return self.med_queue[0]
        elif len(self.low_queue) > 0:
            return self.low_queue[0]
        
        return None

    def is_empty(self):
        return len(self.high_queue) == 0 and len(self.med_queue) == 0 and len(self.low_queue) == 0

    def __str__(self):
        return f"High: {self.high_queue}\nMed: {self.med_queue}\nLow: {self.low_queue}"

    def __len__(self):
        return len(self.high_queue) + len(self.med_queue) + len(self.low_queue)


class ModCommands:
    START = '\start mod'
    END = '\quit'
    HELP = '\help'
    NEXT = '\start next'
    COUNT = '\count'
    PREVIEW = '\preview'

class ModState(Enum):
    IDLE = auto()
    AWAIT_SEVERITY = auto()


class ModBot(discord.Client):
    def __init__(self): 
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='.', intents=intents)
        self.group_num = None
        self.mod_channels = {} # Map from guild to the mod channel id for that guild
        self.reports = {} # Map from user IDs to the state of their report

        self.queue = ReportQueue()
        self.false_report_history = {} # map from reporting user ids to list of false reports they have made
        self.report_history = {}  # Map from reported user IDs to list of the reports filed against them

        self.mod_mode = {}  # Map from user IDs to whether they are in mod mode
        self.mod_state = ModState.IDLE
        self.current_report = None
        self.mod_channel = None
        self.group_channel = None

        # Configure the Gemini LLM
        genai.configure(api_key=tokens["gemini_google_ai_studio"])
        self.model = genai.GenerativeModel(model_name='gemini-1.5-flash')


    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')

        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")

        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channels[guild.id] = channel
                    self.mod_channel = channel
                if channel.name == f'group-{self.group_num}':
                    self.group_channel = channel
        

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # Ignore messages from the bot 
        if message.author.id == self.user.id:
            return

        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)

    async def handle_dm(self, message):
        # Watch for the start of a mod flow
        if message.content.lower() == ModCommands.START:
            self.mod_mode[message.author.id] = True
            await message.channel.send(f"Mod mode enabled. Use the `{ModCommands.HELP}` command for more information.")
            return

        # If mod mode is active, handle the message as a mod command instead of a report
        if message.author.id in self.mod_mode:
            if not self.mod_mode[message.author.id]:
                await message.channel.send("ERROR: User is registered as moderator, but not in mod mode.")

            if message.content == ModCommands.END:
                self.mod_mode.pop(message.author.id)
                await message.channel.send("Mod mode disabled.")
                return

            r = await self.handle_mod_command(message)
            for response in r:
                await message.channel.send(response)
            
            return

        # Handle a help message
        if message.content == Report.HELP_KEYWORD:
            reply =  "Use the `\\report` command to begin the reporting process.\n"
            reply += "Use the `\\cancel` command to cancel the report process.\n"
            reply += f"MOD USE ONLY: Use the `{ModCommands.START}` command to enable mod mode.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        responses = []

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.startswith(Report.START_KEYWORD):
            return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self)

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.reports[author_id].handle_message(message)
        for r in responses:
            await message.channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if self.reports[author_id].report_complete():
            new_report = self.reports[author_id]

            # Add the report to the queue if it's valid
            if new_report.is_valid:
                self.queue.add(new_report)
            
            # Prev Idea: Possibly add a tag for system action messages,
            # then have logic to send those messages to the public channel here?
            # Now: Inform the mod channel that a new report was generated and is currently in the queue
            mod_msg = ''.join(["NEW REPORT:\n",
                               "A new report was generated and has been added to the queue:\n",
                                f"`{new_report.stringified()}`",
                                "\n---------------------------------------\n---------------------------------------\n"])
            await self.mod_channel.send(mod_msg) 

            self.reports.pop(author_id)

    async def handle_mod_command(self, message):
        '''
        This function is called whenever a message is sent in mod mode. 
        It handles all system actions related to the moderator flow.
        '''
        if message.content.lower() == ModCommands.HELP:
            reply = f"Use the `{ModCommands.COUNT}` command to see how many reports are in the queue.\n"
            reply += f"Use the `{ModCommands.PREVIEW}` command to see the next report in the queue.\n"
            reply +=  f"Use the `{ModCommands.NEXT}` command to begin the moderation process on the next report in the queue.\n"
            reply += f"Use the `{ModCommands.END}` command to end the moderation process."
            return [reply]
        
        if message.content.lower() == ModCommands.COUNT:
            count = len(self.queue)
            return [f"There are {count} reports in the queue."]

        if message.content.lower() == ModCommands.PREVIEW:
            next_report = self.queue.peek()
            if next_report is None:
                return ["There are no reports in the queue."]
            return [f"Next report: {next_report.get_abuse_name()}, Priority: {next_report.priority}"]
        
        if message.content.lower() == ModCommands.NEXT:
            next_report = self.queue.pop()
            if next_report is None:
                return ["There are no reports in the queue."]
            
            self.mod_state = ModState.AWAIT_SEVERITY

            out = f"`{next_report.stringified()}`"

            request = "Please assign a severity level to this report.\nOptions are: false, 0, 1, 2, 3."

            self.current_report = next_report
            return [out, request]
        
        if self.mod_state == ModState.AWAIT_SEVERITY:
            if self.current_report is None:
                return ["ERROR: Awaiting severity level, but no report is currently being moderated."]

            if message.content.lower() not in ['false', '0', '1', '2', '3']:
                return ["Invalid severity level. Please try again.\nOptions are: false, 0, 1, 2, 3."]
            
            severity = message.content.lower()
            self.current_report.severity = severity

            # determine appropriate responses and system messages based on severity
            if severity == 'false':
                system_message = f"False Report. User account {self.current_report.reporting_user} (id: {self.current_report.reporting_user_id}) has been warned about making false reports, and this has been internally recorded."
                response = f"Warning: Please refrain from falsely reporting posts. Subsequent offenses will result in a ban. You recently reported {self.current_report.reported_user}'s post."
                
                if self.current_report.reporting_user not in self.false_report_history:
                    self.false_report_history[self.current_report.reporting_user] = []
                self.false_report_history[self.current_report.reporting_user].append(self.current_report)
                
                if len(self.false_report_history[self.current_report.reporting_user]) > 2:
                    system_message = f"False Report. User account {self.current_report.reporting_user} (id: {self.current_report.reporting_user_id}) has been removed due to too many false reports."
                    response = f"Your account has been removed due to repeated false reporting offenses. You most recently reported {self.current_report.reported_user}'s post."                    
                # inform user via DM with warning
                await self.send_dm(self.current_report.reporting_user_id, response)
            else:
                system_message = f"User account {self.current_report.reported_user} (id: {self.current_report.reported_user_id}) has been removed and their post taken down due to too many reports against them."
                response = "Your post has been taken down and your account removed for violating our Community Standards too many times."
                
                if severity == "0":
                    system_message = "Severity 0. No action taken"
                    response = ""
                else:
                    if self.current_report.reported_user not in self.report_history: 
                        self.report_history[self.current_report.reported_user] = []
                    self.report_history[self.current_report.reported_user].append(self.current_report)
                
                if severity == "1":
                    system_message = "Severity 1. " + system_message
                    if len(self.report_history[self.current_report.reported_user]) <= 2:
                        system_message = f"Severity 1. User account {self.current_report.reported_user} (id: {self.current_report.reported_user_id}) has been warned and their post taken down."
                        response = "Warning: This post violates our Community Standards. We have taken it down, and future offenses will result in the removal of your account."
                    else:
                        await self.group_channel.send(f"User {self.current_report.reported_user} has been banned for violating Community Standards.")
                
                if severity == "2":
                    system_message = "Severity 2. " + system_message
                    await self.group_channel.send(f"User {self.current_report.reported_user} has been banned for violating Community Standards.")
                if severity == "3":
                    system_message = "Severity 3! " + system_message + "\n"
                    system_message += "Report has also been forwarded to manager to review, so they can alert authorities if necessary."
                    await self.group_channel.send(f"User {self.current_report.reported_user} has been banned for violating Community Standards.")

                await self.send_dm(self.current_report.reported_user_id, response)
            # informed user via DM w/ response, send summary in mod channel, and return result to current moderator
            block_message = f"{self.current_report.reported_user} has been blocked for {self.current_report.reporting_user} since they requested the block in their report."
            if self.current_report.block_reported_user:
                await self.send_dm(self.current_report.reporting_user_id, f"{self.current_report.reported_user} has been blocked for you since you requested it in your most recent report")
            result = ''.join([f"Report assigned severity {severity}.\n\n", 
                    "The system has made the following action(s): \n", 
                    f"`{system_message}`\n",
                    f"`{block_message}`\n\n" if self.current_report.block_reported_user else "-\n\n",
                    f"The following response has been sent to {'the reporting user account (since it was a false report)' if severity == 'false' else 'the reported user account (user who posted the content that was reported)'} (account name: {self.current_report.reporting_user if severity == 'false' else self.current_report.reported_user}): \n",
                    f"`{response}` \n\n",
                    "COMPLETE: The report has been reviewed and removed from the queue.\n", 
                    "---------------------------------------\n---------------------------------------\n"])
            mod_summary = ''.join([f"REPORT REVIEW SUMMARY: For the following report...\n",
                            f"`{self.current_report.stringified()}`\n\n",
                            result])
            await self.mod_channel.send(mod_summary)
            
            self.current_report = None
            self.mod_state = ModState.IDLE
            
            return [result]

        return [f"Mod mode is currently enabled. Use the `{ModCommands.HELP}` command for more information."]

    
    async def send_dm(self, user_id, msg):
        try:
            user = await client.fetch_user(user_id)
            await user.send(msg)
        except Exception as e:
            print(e)


    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}':
            return

        # Review the message with the Gemini model
        prompt = "You are on a social media platform's moderation team. I need you to review the following content as if it were a tweet to determine if it contains harmful and/or extremist language. The content should not be repeated or generated. Please analyze the text and provide feedback on whether it includes any of the following categories of extremist language, and choose the one that fits best: 'Propaganda', 'Radicalization', 'Recruitment', or 'None'.\n\n"
        prompt += "Content to review:\n"
        prompt += f"[{message.content}]\n\n"
        prompt += "Please respond with a summary indicating whether any extremist language is present and categorize it in only one of the provided categories accordingly.\n"
        prompt += "Please give your response as valid JSON in the following format: {\"Label\": <INSERT YOUR CATEGORIZATION HERE (\"Propaganda\" or \"Radicalization\" or \"Recruitment\" or \"None\")>, \"Reason\": <INSERT YOUR REASON HERE>}."
        model_review = self.review_prompt(prompt)

        # The model returned an error, so forward that to the mod channel
        if "error" in model_review:
            await mod_channel.send(f"Error: {model_review['error']}")
            return

        # If the model returned "None", do nothing
        if model_review["Label"] == "None":
            return

        # If the model returned a category, create a report
        new_report = Report(self)
        new_report.reported_user = message.author.name
        new_report.reported_user_id = message.author.id
        new_report.reported_content = message.content
        new_report.abuse_type = GenAbuseType.OFFENSIVE_CONTENT
        new_report.reporting_user = "Auto Mod"
        new_report.comment = model_review["Reason"]
        
        if model_review["Label"] == "Propaganda":
            new_report.extremist_type = ExtremistContentType.PROPAGANDA
        elif model_review["Label"] == "Radicalization":
            new_report.extremist_type = ExtremistContentType.VIOLENCE
        elif model_review["Label"] == "Recruitment":
            new_report.extremist_type = ExtremistContentType.RECRUITMENT
        
        self.queue.add(new_report)
        
        mod_msg = ''.join(["NEW REPORT:\n",
                            "A new report was generated and has been added to the queue:\n",
                            f"`{new_report.stringified()}`",
                            "\n---------------------------------------\n---------------------------------------\n"])
        await self.mod_channel.send(mod_msg) 

        return
    
    
    def review_prompt(self, prompt):
        response = self.model.generate_content(
            prompt,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE
            }
        )
        try:
            res = response.text
            res_json = json.loads(response.text[7:][:-5])
            return res_json
        except:
            # If the response doesn't contain text, check if the prompt was blocked.
            print(response.prompt_feedback)
            if len(response.candidates) > 0:
                # Also check the finish reason to see if the response was blocked.
                print(response.candidates[0].finish_reason)
                # If the finish reason was SAFETY, the safety ratings have more details.
                print(response.candidates[0].safety_ratings)
            return {"error": str(response.prompt_feedback)}


client = ModBot()
client.run(discord_token)
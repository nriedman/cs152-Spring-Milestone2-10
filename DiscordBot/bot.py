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
    START = 'start mod'
    END = 'quit'
    HELP = 'help'
    NEXT = 'start next'
    COUNT = 'count'
    PREVIEW = 'preview'

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
            await message.channel.send(f"Mode mode enabled. Use the `{ModCommands.HELP}` command for more information.")
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
            reply =  "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
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
            # Nick Comment:
            # Possibly add a tag for system action messages,
            # then have logic to send those messages to the public channel here?

            await message.channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if self.reports[author_id].report_complete():
            new_report = self.reports[author_id]

            # Add the report to the queue if it's valid
            if new_report.is_valid:
                self.queue.add(new_report)

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

            out = "Report: \n"
            out += f"Abuse type: {next_report.get_abuse_name()}\n"
            out += f"Reported User: {next_report.reported_user}\n"
            out += f"Reported By: {next_report.reporting_user}\n"
            out += f"Content: {next_report.reported_content}\n"
            out += f"Additional Comments: {next_report.comment}"

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

            # TODO: Flush out the rest of the system actions here (i.e. second half of the moderation process)
            if severity == 'false':
                system_message = f"False Report. User account {self.current_report.reporting_user} has been warned about making false reports, and this has been internally recorded."
                response = "Warning: Please refrain from falsely reporting posts. Subsequent offenses will result in a ban."
                if self.current_report.reporting_user in self.false_report_history:
                    false_reports = self.false_report_history[self.current_report.reporting_user]
                    if len(false_reports) > 2:
                        system_message = f"False Report. User account {self.current_report.reporting_user} has been removed due to too many false reports."
                        response = "Your account has been removed due to repeated false reporting offenses."
                else:
                    self.false_report_history[self.current_report.reporting_user] = [self.current_report]
            else:
                system_message = ""
                response = "Your post has been taken down and your account removed for violating our Community Standards."
                if severity == '0':
                    system_message = "Severity 0. No action taken"
                    response = ""
                elif severity == "1":
                    if self.current_report.reported_user in self.report_history and len(self.report_history[self.current_report.reported_user]) > 2:
                        system_message = f"Severity 1. User account {self.current_report.reported_user} has been removed and their post taken down due to too many reports against them."
                    else:
                        system_message = f"Severity 1. User account {self.current_report.reported_user} has been warned and their post taken down."
                        response = "Warning: This post violates our Community Standards. We have taken it down, and future offenses will result in the removal of your account."
                elif severity == "2":
                    system_message = f"Severity 2. User account {self.current_report.reported_user} has been removed and their post taken down due to too many reports against them."
                else: # severity == 3
                    system_message = f"Severity 3! User account {self.current_report.reported_user} has been removed and their post taken down due to too many reports against them.\n"
                    system_message += f"Severity 3! Report has also been forwarded to manager to review, so they can alert authorities if necessary."
                if severity != "0":
                    if self.current_report.reported_user not in self.report_history: 
                        self.report_history[self.current_report.reported_user] = []
                    self.report_history[self.current_report.reported_user].append(self.current_report)
            #TODO: how to handle system messages (in what channel sent - mod channel? along with report?)
            # also need to be able to DM responses to reporting user (false report case) and to reported user 
            return [f"Report assigned severity {severity}. Continuing with automatic application of moderation actions."]

    

    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}':
            return

        # Forward the message to the mod channel
        mod_channel = self.mod_channels[message.guild.id]
        await mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')
        scores = self.eval_text(message.content)
        await mod_channel.send(self.code_format(scores))

    
    def eval_text(self, message):
        ''''
        TODO: Once you know how you want to evaluate messages in your channel, 
        insert your code here! This will primarily be used in Milestone 3. 
        '''
        return message

    
    def code_format(self, text):
        ''''
        TODO: Once you know how you want to show that a message has been 
        evaluated, insert your code here for formatting the string to be 
        shown in the mod channel. 
        '''
        return "Evaluated: '" + text+ "'"


client = ModBot()
client.run(discord_token)
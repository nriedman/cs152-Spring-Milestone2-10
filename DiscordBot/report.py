from enum import Enum, auto
import discord
import re

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    MESSAGE_IDENTIFIED = auto()
    REPORT_COMPLETE = auto()
    CONFIRMATION_MESSAGE = auto ()
    ADDITIONAL_COMMENT_PROMPT = auto()
    ADDITIONAL_COMMENTS = auto ()
    BLOCK_USER_PROMPT = auto ()
    OFFENSIVE_CONTENT = auto ()
    EXTREMIST_CONTENT = auto ()
    THREAT = auto ()

class GenAbuseType():
    SPAM = 1
    HARASSMENT = 2
    OFFENSIVE_CONTENT = 3
    THREAT = 4

class OffensiveContentType():
    HATE = 1
    EXPLICIT = 2
    CSAM = 3
    VIOLENT = 4
    EXTREMIST = 5

class ExtremistContentType():
    VIOLENCE = 1
    RECRUITMENT = 2
    PROPAGANDA = 3

class ThreatType():
    SELF = 1
    OTHERS = 2
    PUBLIC = 3
    TERROR = 4

class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        self.reported_message = None
        self.comment = None
        self.step = None
        self.abuse_type = None
        self.offensive_type = None
        self.extremist_type = None
        self.threat_type = None

        self.reported_content = None
        self.reported_user = None
        self.reported_user_id = None
        self.reporting_user = None
        self.reporting_user_id = None
        self.block_reported_user = False

        self.severity = None
        self.is_valid = True
        self.priority = None
        self.result = []
    
    async def handle_message(self, message):
        '''
        This function makes up the meat of the user-side reporting flow. It defines how we transition between states and what 
        prompts to offer at each of those states. You're welcome to change anything you want; this skeleton is just here to
        get you started and give you a model for working with Discord. 
        '''

        if message.content.lower() == self.CANCEL_KEYWORD:
            self.is_valid = False
            self.state = State.REPORT_COMPLETE
            return ["Report cancelled."]
        
        if self.state == State.REPORT_START:
            reply =  "Thank you for starting the reporting process. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.state = State.AWAITING_MESSAGE
            self.reporting_user = message.author.name
            self.reporting_user_id = message.author.id
            return [reply]
        
        if self.state == State.AWAITING_MESSAGE:
            # Parse out the three ID strings from the message link
            m = re.search('/(\d+)/(\d+)/(\d+)', message.content)
            if not m:
                return ["I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."]
            guild = self.client.get_guild(int(m.group(1)))
            if not guild:
                return ["I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."]
            channel = guild.get_channel(int(m.group(2)))
            if not channel:
                return ["It seems this channel was deleted or never existed. Please try again or say `cancel` to cancel."]
            try:
                self.reported_message = await channel.fetch_message(int(m.group(3)))
            except discord.errors.NotFound:
                return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            # Here we've found the message - it's up to you to decide what to do next!
            self.state = State.CONFIRMATION_MESSAGE
            self.reported_content = self.reported_message.content
            self.reported_user = self.reported_message.author.name
            self.reported_user_id = self.reported_message.author.id
            return ["I found this message:", "```" + self.reported_message.author.name + ": " + self.reported_message.content + "```", 
                        "Is this the message you want to report? (yes/no)"]

        if self.state == State.CONFIRMATION_MESSAGE:
        # ask the user to confirm if this is the message they wanted to report
            if message.content.lower() not in ["yes", "no"]:
                return ["Please respond with yes or no only."]

            if message.content.lower() == "no":
                self.state = State.AWAITING_MESSAGE
                self.reported_content = None
                self.reported_user = None
                self.reported_user_id = None
                return ["I'm sorry, please verify the link and try again?"]

            if message.content.lower() == "yes":
                self.state = State.MESSAGE_IDENTIFIED
                confirmed = "Thank you for confirming! Please answer a few questions so that we can better assist you."
                reply = "Please select a reason for reporting this user (Enter the corresponding number):\n"
                types = [
                    "Spam",
                    "Harassment",
                    "Offensive Content",
                    "Imminent Safety Threat"
                ]
                for i, option in enumerate(types, start=1):
                    reply += f"{i}. {option}\n"
                return [confirmed, reply]

        if self.state == State.MESSAGE_IDENTIFIED:
            if message.content not in ['1', '2', '3', '4']:
                return ["Please enter a valid number (1, 2, 3, 4)"]
            
            self.abuse_type = int(message.content)
            if self.abuse_type == GenAbuseType.SPAM or self.abuse_type == GenAbuseType.HARASSMENT:
                self.state = State.ADDITIONAL_COMMENT_PROMPT
                return ["Would you like to provide additional comments or include any direct messages?"]
            
            if self.abuse_type == GenAbuseType.OFFENSIVE_CONTENT:
                self.state = State.OFFENSIVE_CONTENT
                reply = "Please select the category this offensive content best fits into (Enter the corresponding number):\n"
                types = [
                    "Hate Speech",
                    "Sexually Explicit Content",
                    "Child Sexual Abuse Material",
                    "Violent / Graphic Content",
                    "Extremist Content"
                ]
                for i, option in enumerate(types, start=1):
                    reply += f"{i}. {option}\n"
                return [reply]
            
            if self.abuse_type == GenAbuseType.THREAT:
                self.state = State.THREAT
                reply = "Please select the category this imminent safety threat best fits into (Enter the corresponding number):\n"
                types = [
                    "Threat to Self",
                    "Threat to Others",
                    "Public Safety Concern",
                    "Terrorist Attack"
                ]
                for i, option in enumerate(types, start=1):
                    reply += f"{i}. {option}\n"
                return [reply]
        
        if self.state == State.OFFENSIVE_CONTENT:
            if message.content not in ['1', '2', '3', '4', '5']:
                return ["Please enter a valid number (1, 2, 3, 4, 5)"]
            
            self.offensive_type = int(message.content)
            
            if self.offensive_type != OffensiveContentType.EXTREMIST:
                reply = ""
                if self.offensive_type == OffensiveContentType.VIOLENT:
                    reply += "We will review the violent content and take appropriate action, such as post and/or account removal.\n"
                reply += "Would you like to provide additional comments or include any direct messages?"

                self.state = State.ADDITIONAL_COMMENT_PROMPT
                return [reply]
            else:
                self.state = State.EXTREMIST_CONTENT
                reply = "Please select the category this extremist content best fits into (Enter the corresponding number):\n"
                types = [
                    "Violence",
                    "Recruitment",
                    "Propaganda"
                ]
                for i, option in enumerate(types, start=1):
                    reply += f"{i}. {option}\n"
                return [reply]
        
        if self.state == State.EXTREMIST_CONTENT:
            if message.content not in ['1', '2', '3']:
                return ["Please enter a valid number (1, 2, 3)"]
            
            self.extremist_type = int(message.content)

            reply = ""
            keyword = ""
            if self.extremist_type == ExtremistContentType.PROPAGANDA:
                keyword = "propaganda"
            if self.extremist_type == ExtremistContentType.RECRUITMENT:
                keyword = "recruitment"
                reply += "We recommend contacting law enforcement and sharing any recruitment direct messages received.\n"
            if self.extremist_type == ExtremistContentType.VIOLENCE:
                keyword = "violence"
            reply += "We will review the " + keyword + " content and take appropriate action, such as post and/or account removal.\n"
            reply += "Would you like to provide additional comments or include any direct messages?"
            
            self.state = State.ADDITIONAL_COMMENT_PROMPT
            return [reply]

        if self.state == State.THREAT:
            if message.content not in ['1', '2', '3', '4']:
                return ["Please enter a valid number (1, 2, 3, 4)"]
            
            self.threat_type = int(message.content)

            reply = "We recommend contacting law enforcement immediately and sharing any information you have.\n"
            reply += "We will also examine the content and take appropriate action, such as post and/or account removal.\n"
            reply += "Would you like to provide additional comments or include any direct messages?"

            self.state = State.ADDITIONAL_COMMENT_PROMPT
            return [reply]
        
        if self.state == State.ADDITIONAL_COMMENT_PROMPT:
            if message.content.lower() not in ["yes", "no"]:
                return ["Please respond with yes or no only."]

            if message.content.lower() == "no":
                self.state = State.BLOCK_USER_PROMPT
                return ["Would you like to block the user who posted this content?"]

            if message.content.lower() == "yes":
                self.state = State.ADDITIONAL_COMMENTS
                return ["Please attach any relevant photos, links, and/or additional information in a single message."]

        if self.state == State.ADDITIONAL_COMMENTS:
            self.comment = message.content
            self.state = State.BLOCK_USER_PROMPT
            return ["Would you like to block the user who posted this content?"]

        if self.state == State.BLOCK_USER_PROMPT:
            if message.content.lower() not in ["yes", "no"]:
                return ["Please respond with yes or no only."]
            reply = "Thank you for completing this report.\n"
            reply += "Our content moderation team will review this post and decide on an appropriate action."
            self.state = State.REPORT_COMPLETE
            if message.content.lower() == "yes":
                self.block_reported_user = True
                reply += "\n" + self.reported_message.author.name + " has been blocked."
            return [reply]


    def report_complete(self):
        return self.state == State.REPORT_COMPLETE
    
    def get_abuse_name(self):
        if self.abuse_type == GenAbuseType.SPAM:
            return "Spam"
        if self.abuse_type == GenAbuseType.HARASSMENT:
            return "Harassment"
        if self.abuse_type == GenAbuseType.OFFENSIVE_CONTENT:
            return "Offensive Content"
        if self.abuse_type == GenAbuseType.THREAT:
            return "Imminent Safety Threat"

    def __str__(self):
        out = "Report: \n"
        out += f"Abuse type: {self.get_abuse_name()}\n"
        out += f"Reported User: {self.reported_user} (id: {self.reported_user_id})\n"
        out += f"Reported By: {self.reporting_user} (id: {self.reporting_user_id})\n"
        out += f"Block Requested: {'Yes' if self.block_reported_user else 'No'}\n"
        out += f"Content: {self.reported_content}\n"
        out += f"Additional Comments: {self.comment}"
        return out
    
    def stringified(self):
        return self.__str__()

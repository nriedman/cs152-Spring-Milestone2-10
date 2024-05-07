from enum import Enum, auto
import discord
import re

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    MESSAGE_IDENTIFIED = auto()
    REPORT_COMPLETE = auto()
    CONFIRMATION_MESSAGE = auto ()

class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        self.reported_message = None
        self.step = None
        self.abuse_type = None
        self.result = []
    
    async def handle_message(self, message):
        '''
        This function makes up the meat of the user-side reporting flow. It defines how we transition between states and what 
        prompts to offer at each of those states. You're welcome to change anything you want; this skeleton is just here to
        get you started and give you a model for working with Discord. 
        '''

        if message.content == self.CANCEL_KEYWORD:
            self.state = State.REPORT_COMPLETE
            return ["Report cancelled."]
        
        if self.state == State.REPORT_START:
            reply =  "Thank you for starting the reporting process. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.state = State.AWAITING_MESSAGE
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
                message = await channel.fetch_message(int(m.group(3)))
            except discord.errors.NotFound:
                return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            # Here we've found the message - it's up to you to decide what to do next!
            self.state = State.MESSAGE_IDENTIFIED

            if self.state == State.CONFIRMING_MESSAGE:
            # ask the user to confirm if this is the message they wanted to report
                if self.abuse_type == None:
                    confirmation_prompt = "I found this message:", "\n" + self.reported_message.author.name + ": " + self.reported_message.content + "\n", "Is this the message you want to report? (yes/no)"
                    self.abuse_type = 0
                    return [confirmation_prompt]

                if message.content.lower() not in ["Yes", "No"]:
                    self.abuse_type = 0
                    return ["Please respond appropriately (ONLY yes or no)."]

                if message.content.lower() == "No":
                    self.state = State.AWAITING_MESSAGE
                    self.abuse_type = None
                    return ["I'm sorry, I couldn't find the message you mentioned. Could you please verify the link and send it again?"]

                if message.content.lower() == "Yes":
                    self.state = State.MESSAGE_IDENTIFIED
                    self.result.append(self.reported_message)
                    self.abuse_type = None

            if self.state == State.MESSAGE_IDENTIFIED:
                if self.abuse_type == None:
                    confirmed = "Thank you for confirming! Please answer a few questions so that we can better assist you."
                    reply = "Please select a reason for reporting this user (Enter the corresponding number):\n"
                    types = [
                        "Spam",
                        "Harassment",
                        "Offensive Content",
                    ]
                    for i, option in enumerate(options, start=1):
                        reply += f"{i}. {option}\n"
                    self.abuse_type = 1
                    return [confirmed, reply]

                if self.abuse_type == 1:
                    if message.content not in ['1', '2', '3', '4']:
                        return ["Please enter only a valid number (1, 2, 3, 4)"]
                    self.abuse_type = 2
                    self.message = message
                
                #Spam 
                if self.message.content == "1":
                    if self.abuse_type == 2:
                        response = "Would you like to provide additional comments or include any direct messages?"
                return [confirm, reply]

                #Harassment
                if self.message.content == "2":
                    if self.abuse_type == 2:
                #Offensive Content
                

            
            

            return ["<insert rest of reporting flow here>"]

            return ["I found this message:", "```" + message.author.name + ": " + message.content + "```", \
                    "This is all I know how to do right now - it's up to you to build out the rest of my reporting flow!"]
        

        return []

    def report_complete(self):
        return self.state == State.REPORT_COMPLETE
    


    


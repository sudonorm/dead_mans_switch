import json
import os
import sys
import warnings
warnings.filterwarnings("ignore")
import telegram
import datetime
import time
from telegram.constants import MAX_MESSAGE_LENGTH
from typing import List, Union, Dict, Any

import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email import encoders
from email.mime.base import MIMEBase

import boto3
import dropbox
from io import StringIO, BytesIO

AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY")
AWS_REGION = os.environ.get("AWS_REGION")
DROPBOX_ACCESS_TOKEN = os.environ.get("DROPBOX_ACCESS")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_CHAT_ID"))
SENDER_EMAIL = os.environ.get("EMAIL_USERNAME")
SENDER_PASS = os.environ.get("EMAIL_PASSWORD")
PORT_NUMBER = os.environ.get("SMTP_PORT")
SMTP_SERVER = os.environ.get("SMTP_SERVER")
RECEIVER_EMAIL = os.environ.get("EMAIL_USERNAME")
RECEIVER_EMAIL1 = os.environ.get("EMAIL1")
RECEIVER_EMAIL2 = os.environ.get("EMAIL2")
RECEIVER_EMAIL3 = os.environ.get("EMAIL3")
LINK = os.environ.get("LINK")

class EmailSender:
    """ This class contains a function which can be used to send an email via smtp.    
    """
    def __init__(self):
        pass
    
    def send_email(self, *, subject: str, messagePlainText: str, addHtml: bool = False, messageHtml: str = "", smtp_server: str, port: int, 
                   sender_email: str, password: str, receiver_emails: List = [], addAttachment: bool = False, 
                   attachmentFileName: str = "test.csv"):

        '''
            This function can be used to send an email via smtp. It also allows for the addition of attachments, currently pdfs and csvs have been tested to work. 
            
            It is set up to automatically bcc the sender a copy of the email, but this can be changed.
            
            Adapted from: https://realpython.com/python-send-email/
        '''
        
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = sender_email
        message["To"] = ", ".join(receiver_emails)
        message["Bcc"] = sender_email

        # Turn this into plain MIMEText objects
        part1 = MIMEText(messagePlainText, "plain")
        # Add HTML/plain-text parts to MIMEMultipart message
        # The email client will try to render the last part first
        message.attach(part1)

        if addHtml:
            if not messageHtml == "":
                # Turn this into html MIMEText objects
                part2 = MIMEText(messageHtml, "html")
                message.attach(part2)

        if addAttachment:
            filename = attachmentFileName  # Must be in same directory as script

            # Open file in binary mode
            with open(filename, "rb") as attachment:
                # Add file as application/octet-stream
                # Email client can usually download this automatically as attachment
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())

            # Encode file in ASCII characters to send by email    
            encoders.encode_base64(part)

            # Add header as key/value pair to attachment part
            part.add_header(
                "Content-Disposition",
                f"attachment; filename= {filename}",
            )

            # Add attachment to message
            message.attach(part)

        # Convert message to string
        messageText = message.as_string()

        # Create secure connection with server and send email
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(
                sender_email, receiver_emails, messageText
            )

class TelegramSidekick:
    """This class contains functions which can be used to send messages to a Telegram bot
    """

    def __init__(self, token:str = None):
        self.token = token
    
    def _send_message(self, bot: telegram.Bot, message:str, chat_id:int):
        return bot.send_message(chat_id=chat_id, text=message, parse_mode=None, disable_notification=False, disable_web_page_preview=False)

    def send_message(self, *, messages:List = None, chat_id:int = None, timeout:int = 30):
        """Send message to Telegram bot. """
        
        request = telegram.utils.request.Request(read_timeout=timeout)
        bot = telegram.Bot(self.token, request=request)
        
        for msg in messages:
            msg = str(msg)
            
            if len(msg) == 0:
                continue
            elif len(msg) > MAX_MESSAGE_LENGTH:
                warnings.warn("This message is longer than the MAX_MESSAGE_LENGTH=%d. Let us split this into smaller messages, shall we?" % MAX_MESSAGE_LENGTH)
                ms = self.chunk_message(msg, MAX_MESSAGE_LENGTH)
                for msg in ms:
                    self._send_message(bot, msg, chat_id)
            else:
                self._send_message(bot, msg, chat_id)

    def chunk_message(self, msg: List, max_length: int) -> List:
        """Chunk up a long message into smaller messages which are less than the maximum length."""
        
        ms = []
        msg = str(msg)
        while len(msg) > max_length:
            ms.append(msg[:max_length])
            msg = msg[max_length:]
        ms.append(msg)
        return ms

    def get_latest_message(self, *, timeout:int = 30):
        """Get the last message sent to a Telegram bot as well as its timestamp"""
        
        request = telegram.utils.request.Request(read_timeout=timeout)
        bot = telegram.Bot(self.token, request=request)
        
        message, dateSent, updates = "", "", []
        
        updates = bot.get_updates(timeout=30)
        
        if not len(updates) == 0:

            dateSent = updates[0]["message"]["date"].strftime('%Y-%m-%d')
            message = updates[0]["message"]["text"]
            
            return message, dateSent, updates
        else:
            #print("No new messages were fetched. The last message sent to your bot needs to have been sent within the last 24 hours, or less, in order to be able to fetch data. Please send a message to the bot and try again.")
            return message, dateSent, updates

    def get_chat_id(self, *, timeout:int = 30):
        """Get the chat id of a Telegram bot"""
        
        message, dateSent, updates = self.get_latest_message(timeout=timeout)

        if not len(updates) == 0:
            return updates[0].message.from_user.id
        else:
            return "no new message found"
            #print("Unable to grab the bot's chat id. The last message sent to your bot needs to have been sent within the last 24 hours, or less, in order to be able to fetch data. Please send a message to the bot and try again.")
            
    def send_chat_id(self):
        """Send chat id as a message to your Telegram bot"""
        chatId = self.get_chat_id()
        
        if isinstance(chatId, int):
            self.send_message(messages = [chatId], chat_id = int(chatId))

class DBXUpDown:
    """This class contains functions which can be used to download and upload a JSON file to a Dropbox account
    """
    
    def __init__(self, token: str):
        self.dbx = dropbox.Dropbox(token)
        if (len(token) == 0):
            sys.exit("ERROR: Looks like you didn't add your access token. Add your Dropbox token to the instance of your class and try again.")
    
    def data_template(self):
        return {"source": "from aws", "lastMessage": "", "status": "not checked in", "emailSent": "no", "lastChecked": datetime.datetime.now(), "noOfDaysElapsed": 1}

    def default(self, o: Any):
        '''
        Convert datetime and date objects into isoformat so they can be serialized.
        '''
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()

    def add_to_dropbox(self, data: Dict, filename: str):
        """Add a JSON file to Dropbox
        """
        
        pa_th = '/{}'.format(filename)
        while '//' in pa_th:
            pa_th = pa_th.replace('//', '/')
        
        try:
            with StringIO() as stream:
                json.dump(data, stream, indent=4, default=self.default)

                stream.seek(0)
            
                self.dbx.files_upload(
                    f=stream.read().encode(),
                    path=pa_th,
                    mode=dropbox.files.WriteMode.overwrite
                )
                
        except Exception as e:
            sys.exit(f'{"ERROR: the following exception occured: "}{e}')
    
    def get_from_dropbox(self, filename: str) -> Dict:
        """Download a file from Dropbox.
        Return the bytes of the file, or None if it doesn't exist.
        """
        
        # dbx = dropbox.Dropbox(self.token)
        pa_th = '/{}'.format(filename)
        while '//' in pa_th:
            pa_th = pa_th.replace('//', '/')
        
        try:
            md, res = self.dbx.files_download(pa_th)
        except:
            return None
        data = res.content
        return data

    def get_or_create_db(self):
        """This function will try to get a JSON file from Dropbox and 
        if it does not exist, it will copy our template and add this to Dropbox
        """
        
        newDump = False
        dataTemplate = self.data_template()
        bytes_data = self.get_from_dropbox("dmsDB.json")

        if bytes_data == None:
            self.add_to_dropbox(dataTemplate, "dmsDB.json")
            newDump = True
            return dataTemplate, newDump
        
        else:
            with BytesIO(bytes_data) as stream:
                data = json.load(stream)
            return data, newDump

def lambda_handler(event, context):
    """This function should be used on AWS in a Lambda function
    """
    ### layer update: https://docs.aws.amazon.com/lambda/latest/dg/python-layers.html
    ### use cloudshell to create the layer
    
    dbx = DBXUpDown(DROPBOX_ACCESS_TOKEN)
    tel = TelegramSidekick(TELEGRAM_TOKEN)
    email = EmailSender()
            
    # Create the plain-text and HTML version of your message
    text = """\
    some message here""".format(LINK)

    html = """\
    <html>
    <body>
        <p>some message here<br><br>
        
        </p>
    </body>
    </html>
    """.format(LINK)
        
    deets, new = dbx.get_or_create_db()

    noOfDaysElapsed = deets["noOfDaysElapsed"]
    status = deets["status"]
    emailSent = deets["emailSent"]

    try:
        message, dateSent, updates = tel.get_latest_message()
    except:
        updates = []

    if noOfDaysElapsed == (42 * 2) and status == "not checked in" and emailSent == "no":
        print("sending email")
        email.send_email(subject = "One last time...", messagePlainText = text, addHtml = True, messageHtml = html, smtp_server = SMTP_SERVER, port = PORT_NUMBER, sender_email = SENDER_EMAIL, password = SENDER_PASS, receiver_emails = [RECEIVER_EMAIL1, RECEIVER_EMAIL2])
        
        noOfDaysElapsed += 1
        deets["emailSent"] = "yes"
        deets["noOfDaysElapsed"] = noOfDaysElapsed
        deets["lastChecked"] = datetime.datetime.now()
        dbx.add_to_dropbox(deets, "dmsDB.json")

    elif noOfDaysElapsed < (42 * 2) and len(updates) != 0 and status == "not checked in":
        noOfDaysElapsed += 1
        deets["lastMessage"] = updates[0]['message']['text']
        deets["status"] = "checked in"
        deets["noOfDaysElapsed"] = noOfDaysElapsed
        deets["lastChecked"] = datetime.datetime.now()
        dbx.add_to_dropbox(deets, "dmsDB.json")
    
    elif noOfDaysElapsed >= (42 * 2) and emailSent in ["yes", "no"] and status in ["checked in", "not checked in"]:
        dataTemplate = dbx.data_template()
        dbx.add_to_dropbox(dataTemplate, "dmsDB.json")

    else:
        if status == "not checked in":
            tel.send_message(messages = ["Please check in"], chat_id = int(TELEGRAM_CHAT_ID))
        
        if not new:  
            noOfDaysElapsed += 1
            
        deets["noOfDaysElapsed"] = noOfDaysElapsed
        deets["lastChecked"] = datetime.datetime.now()
        dbx.add_to_dropbox(deets, "dmsDB.json")
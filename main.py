from dotenv import load_dotenv
import os
from cah.bot import bot

load_dotenv()

bot.run(os.environ.get("TOKEN"))

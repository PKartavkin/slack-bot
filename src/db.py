from pymongo import MongoClient
import os

client = MongoClient(os.environ["MONGO_URL"])
db = client["slackbot"]
orgs = db["organizations"]

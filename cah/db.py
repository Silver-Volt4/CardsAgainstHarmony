from peewee import *

db = SqliteDatabase("cards.db")


class BaseModel(Model):
    class Meta:
        database = db


class Deck(BaseModel):
    name = CharField()
    guild_id = IntegerField(null=True)


class WhiteCard(BaseModel):
    deck = ForeignKeyField(Deck, backref="white_cards")
    text = CharField()


class BlackCard(BaseModel):
    deck = ForeignKeyField(Deck, backref="black_cards")
    text = CharField()
    white_card_num = IntegerField(null=True)

    def get_white_card_num(self):
        return self.white_card_num or 1


db.create_tables([Deck, WhiteCard, BlackCard])

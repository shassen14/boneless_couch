# couchd/platforms/twitch/components/welcome_messages.py
import random


def _tier_label(tier: str) -> str:
    return {"1000": "Tier 1", "2000": "Tier 2", "3000": "Tier 3"}.get(str(tier), f"Tier {tier}")


_FOLLOW_POOL = [
    "{name} just followed! Welcome to the couch 🛋️",
    "Welcome {name}! Glad you're here 👋",
    "{name} dropped a follow! Thanks for joining the community 🙌",
    "Say hi to {name}! Fresh follow in the building 🛋️",
]

_SUB_POOL = [
    "{name} just subscribed ({tier})! Welcome to the squad 🎉",
    "Huge welcome to {name} for the {tier} sub! 🛋️",
    "{name} is now a subscriber ({tier})! Thank you so much! 🙏",
    "Welcome {name} to the couch family! ({tier}) 🎊",
]

_RESUB_POOL = [
    "{name} has been on the couch for {months} month(s)! ({tier}) Thanks for sticking around 🛋️",
    "{months} months with {name}! Appreciate you ({tier}) 🙏",
    "{name} resubbed for month {months}! ({tier}) Couch loyalty on point 🎉",
]

_GIFT_POOL = [
    "{gifter} just gifted {count} sub(s)! What a legend 🎁",
    "Holy moly! {gifter} dropped {count} gift sub(s)! 🎉",
    "{gifter} being generous with {count} sub(s)! Thank you! 🙏",
]

_BITS_POOL = [
    "{name} just cheered {bits} bit(s)! 💎 Thank you!",
    "{bits} bit(s) from {name}! You're a gem 💎",
    "Thank you {name} for the {bits} bit(s)! 🙌",
]

_RAID_POOL = [
    "{raider} is raiding with {count} viewer(s)! Welcome in everyone 🚀",
    "Incoming raid from {raider} and {count} friend(s)! 🎊 Welcome to the couch!",
    "RAID ALERT! {raider} brought {count} people! Welcome welcome welcome 🛋️",
]


def follow_message(display_name: str) -> str:
    return random.choice(_FOLLOW_POOL).format(name=display_name)


def sub_message(display_name: str, tier: str) -> str:
    return random.choice(_SUB_POOL).format(name=display_name, tier=_tier_label(tier))


def resub_message(display_name: str, months: int, tier: str) -> str:
    return random.choice(_RESUB_POOL).format(name=display_name, months=months, tier=_tier_label(tier))


def giftbomb_message(gifter_display_name: str, count: int) -> str:
    return random.choice(_GIFT_POOL).format(gifter=gifter_display_name, count=count)


def bits_message(display_name: str, bits: int) -> str:
    return random.choice(_BITS_POOL).format(name=display_name, bits=bits)


def raid_message(from_display_name: str, viewer_count: int) -> str:
    return random.choice(_RAID_POOL).format(raider=from_display_name, count=viewer_count)

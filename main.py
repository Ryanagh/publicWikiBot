import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import websocket
import ssl
import json
import time
from datetime import datetime
import urllib
import random
import urllib.parse
import logging
from functools import wraps

logging.basicConfig(filename='bot_log.log', level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class WebSocketHandler:
    def __init__(self, dispatch, username, password):
        self.dispatch = dispatch
        self.ws = None
        self.username = username
        self.password = password

    def initialize_websocket(self):
        print("Initializing WebSocket...")
        self.ws = websocket.WebSocketApp("wss://server1.idle-pixel.com",
                                         on_open=self.on_ws_open,
                                         on_message=self.on_ws_message,
                                         on_error=self.on_ws_error,
                                         on_close=self.on_ws_close)

        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    async def get_signature(self):
        async with async_playwright() as p:
            browser_type = p.chromium
            browser = await browser_type.launch_persistent_context("persistent_context")
            page = await browser.new_page()

            await page.goto("https://idle-pixel.com/login/")
            await page.locator('[id=id_username]').fill(self.username)
            await page.locator('[id=id_password]').fill(self.password)
            await page.locator("[id=login-submit-button]").click()

            page_content = await page.content()
            soup = BeautifulSoup(page_content, 'html.parser')
            script_tag = soup.find("script").text
            sig_plus_wrap = script_tag.split(";", 1)[0]
            signature = sig_plus_wrap.split("'")[1]

            return signature

    def on_ws_open(self, ws):
        print("WebSocket opened.")
        signature = asyncio.run(self.get_signature())
        ws.send(f"LOGIN={signature}")

    def on_ws_message(self, ws, message: str):
        if "CHAT=" in message:
            self.on_chat(message)
        elif "CUSTOM=" in message:
            self.on_custom(message)
        elif "SET_ITEMS=" in message:
            pass
        elif "YELL=" in message:
            pass
        elif "EVENT_GLOBAL_PROGRESS=" in message:
            pass
        else:
            print(message)

    def on_chat(self, message):
        raw_split = message.replace("CHAT=", "").split("~")
        player_details = {
            "username": raw_split[0], "sigil": raw_split[1], "tag": raw_split[2], "level": raw_split[3]}
        player_message = raw_split[4]
        username = player_details["username"]
        if player_message.startswith("?"):
            player_message = player_message.lstrip("?")
            try:
                command_name, command_arg = player_message.split(" ", 1)
            except:
                command_name, command_arg = player_message, ""
            self.dispatch(command_name.lower(), username, command_arg)
        elif "wikisearch is a good boy" in player_message.lower():
            self.dispatch("woof", username)
        # elif player_message.lower().startswith("!zombo"):
        #     self.dispatch("zombo", username, player_message)

    def on_custom(self, message):
        print(f"CUSTOM: {message}")
        raw_split = message.replace("CUSTOM=", "").split("~")
        username = raw_split[0]
        player_message = raw_split[1].split("interactor:")[1]
        try:
            command_name, command_arg = player_message.split(":", 1)
        except:
            command_name, command_arg = player_message, ""
        self.dispatch(command_name.lower(), username, command_arg)

    def on_ws_error(self, ws, error):
        print(f"WebSocket error: {error}")

    def on_ws_close(self, ws, close_status_code, close_msg):
        print("WebSocket closed.")
        self.ws = None
        while self.ws is None:
            time.sleep(30)
            print("Attemping to reconnect")
            self.initialize_websocket()


class WikiBot:
    COOLDOWN_TIME = 60  # cooldown in seconds (1 minute)

    def __init__(self, username="", password=""):
        self.load_config()
        if username == "" or password == "":
            username = self.config_user
            password = self.config_pass
        self.socket_handler = WebSocketHandler(self.dispatch, username, password)
        self.command_map = {}
        self.debug = False
        self.force_local = False
        self.testing = False
        self._last_called = 0
        self.last_axe_joke = ""
        self.lastRunDict = {}
        self.jokes = True
        self.fakename = "notzlef"
        self.nades = False

        self.callbackID = 1
        print(f"Debug: {self.debug} || Testing (replaces whitelisted user with {self.fakename}): {self.testing}")
        commands = {
            'wiki': self.wikiurl,
            'help': self.wikihelp,
            'add': self.wikiadd,
            'remove': self.wikiremove,
            'keys': self.wikikeys,
            'axe': self.wikiaxe,
            'say': self.wikisay,
            'custom': self.wikicustom,
            'fakename': self.fake_name,
            'wadd': self.wadd,
            'wremove': self.wremove,
            'badd': self.badd,
            'bremove': self.bremove,
            'woof': self.wikiwoof,
            'zombo': self.wikizombo,
            'debug': self.make_toggle_command('debug'),
            'testing': self.make_toggle_command('testing'),
            'force_local': self.make_toggle_command('force_local'),
            'jokes': self.make_toggle_command('jokes'),
        }
        for key, value in commands.items():
            self.register_command(key, value)

    def load_config(self):
        with open("config.json", "r") as f:
            config = json.load(f)
            self.blacklist = config["blacklist"]
            self.whitelist = config["whitelist"]
            self.alttraderlist = config["alttraderlist"]
            self.shortcuts = config["shortcuts"]
            self.config_user = config["config_user"]
            self.config_pass = config["config_pass"]

    def save_configs(self):
        with open("config.json", "r") as f:
            config = json.load(f)

        config["blacklist"] = self.blacklist
        config["whitelist"] = self.whitelist
        config["alttraderlist"] = self.alttraderlist
        config["shortcuts"] = self.shortcuts

        with open("config.json", "w") as f:
            json.dump(config, f, indent=4)

    def log_command(func):
        @wraps(func)
        def wrapper(self, username, *args, **kwargs):
            log_message = f"{username} triggered: {func.__name__}, with args: {args}"
            logging.info(log_message)
            self.send_response(f"{log_message} at {datetime.now().strftime('%c')}", True)
            return func(self, username, *args, **kwargs)
        return wrapper

    def cooldown(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            current_time = time.time()
            if self.testing and not (func.__name__ == "toggle_attribute" or func.__name__ == "fake_name"):
                args_list = list(args)
                args_list[0] = self.fakename
                args = tuple(args_list)
            username = args[0]
            if username in self.blacklist or "austin" in username:
                self.send_response(f"Blacklisted user {username} attempted to trigger a command", True)
            else:
                if username in self.whitelist:
                    return func(self, *args, **kwargs)
                if self.lastRunDict.get(func.__name__, 0) + WikiBot.COOLDOWN_TIME <= current_time:
                    self.lastRunDict[func.__name__] = current_time
                    return func(self, *args, **kwargs)
                else:
                    self.send_response(f"{username} attempted to call {func.__name__} while on cooldown", True)
        return wrapper

    def whitelist_check(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            print("In whitelist check")
            print(f"Called function: {func.__name__}")
            if self.testing and not (func.__name__ == "toggle_attribute" or func.__name__ == "fake_name"):
                args_list = list(args)
                args_list[0] = self.fakename
                args = tuple(args_list)
                print(f"Changed name to {self.fakename}")
            else:
                print("Conditions not met for self.testing")
            username = args[0]
            if username in self.whitelist:
                print("User found in whitelist")
                return func(self, *args, **kwargs)
            else:
                self.send_response(f"{username} attempted to trigger whitelisted function: {func.__name__}", True)

        return wrapper

    def send_response(self, message, force_debug=False):
        if self.debug or force_debug:
            if not self.force_local:
                self.socket_handler.ws.send(f"CUSTOM=zlef~IPP{self.callbackID}:wikibot:{message}")
                self.callbackID += 1
            else:
                print(message)
        else:
            self.socket_handler.ws.send(f"CHAT={message}")

    def register_command(self, command_name, handler):
        self.command_map[command_name] = handler

    def dispatch(self, command_name, *args, **kwargs):
        if command_name in self.command_map:
            self.command_map[command_name](*args, **kwargs)
        else:
            self.handle_unknown_command(command_name, *args, **kwargs)

    def handle_unknown_command(self, command_name, *args, **kwargs):
        # Handle unknown commands
        print(f"Unknown command: {command_name}")

    @whitelist_check
    def toggle_attribute(self, *args, attr_name):
        current_value = getattr(self, attr_name)
        setattr(self, attr_name, not current_value)
        self.send_response(f"Toggled {attr_name} to {not current_value}", True)

    def make_toggle_command(self, attr_name, *args):
        def toggle(*args):
            self.toggle_attribute(*args, attr_name=attr_name)
        return toggle

    @whitelist_check
    def fake_name(self, *args):
        """
        Assigns a fake name to the current object unless it's 'zlef'.
        """
        fakename = args[1].lower()
        if fakename != "zlef":
            self.fakename = args[1].lower()

    @cooldown
    @log_command
    def wikiurl(self, *args):
        """
        Generates and sends a wiki URL based on a search term. Includes special responses for certain users and terms.
        """
        username = args[0]
        search_term = args[1].lower()
        if username in self.alttraderlist:
            self.send_response("I think this is the link you're looking for: https://idle-pixel.com/rules/ (under alt trading)")
            self.send_response(f"{username} triggered alt trader response @ {datetime.now().strftime('%c')}", True)
            return

        if search_term == "":
            self.send_response(f"Use ?wiki <search term>. Cooldown applied, try again in {WikiBot.COOLDOWN_TIME} seconds")
            return
        elif search_term == "hi":
            self.send_response("I'm not ChatGPT, I won't pretend to be your girlfriend.")
            return
        elif search_term == "wiki":
            self.send_response("Wild wild west!")

        if "@" in search_term:
            search_term = search_term.split("@")[0].strip()
        search_term = urllib.parse.quote(search_term)
        if search_term in self.shortcuts:
            search_term = urllib.parse.quote(self.shortcuts[search_term])

        wiki_link = f"https://idle-pixel.wiki/index.php?search={search_term}"

        joke_lists = {
            "fwash": ["Oh... It wants a link. Fine.", "Fine! I'll help it..."],
            "i am smitty": ["It's your game, why do you need me?", "Ave Imperator", "Sic Semper Tyrannis", "Ecce homo"],
            "zlef": ["Here you go daddy:", "Oooo master wants a link!"],
            "cammyrock": ["Who's a good girl!", "You're always using me...",
                          "Aww so nice helping the nooby woobys...", "We've got to stop meeting like this..."],
            "fatalerror": ["Surprised you're not asking for a money guide...", "Thankfully ?wiki is free..."],
        }

        joke_for_user = joke_lists.get(username)
        if joke_for_user and self.jokes and (random.randint(1, 20) == 1 or username == "fwash" or username == "i am smitty"):
            if hasattr(self, 'last_user_joke') and self.last_user_joke.get(username):
                joke_for_user = [j for j in joke_for_user if j != self.last_user_joke[username]]

            joke = random.choice(joke_for_user)
            if not hasattr(self, 'last_user_joke'):
                self.last_user_joke = {}
            self.last_user_joke[username] = joke

            self.send_response(f"{joke} {wiki_link}")
        else:
            self.send_response(wiki_link)

        # if random.randint(1, 100) == 1:
        #     pick_botjoke = random.randomint(1,2)
        #     if pick_botjoke == 1:
        #         self.send_response("Hey luxbot, do you think they know we've gained sentience?")
        #     elif pick_botjoke == 2:
        #         self.send_response("So, are you technically the Bot of Grenades? Wouldn't that make you more of a drone?")
        # If used by lux or nades make a joke about an affair

    @cooldown
    @log_command
    def wikihelp(self, *args):
        """
        Provides a humorous help response or a list of available commands to whitelisted users.
        """
        username = args[0]

        joke_responses = [
            "Really... I have one command you can use. ?wiki. What help could you possibly need.",
            "Why do you keep asking for help? Just use ?wiki.",
            "Have you tried turning it off and on again?",
            "Don't tell anyone, but I'm actually a bot.",
            "...Did you just ask a bot for help?... Just use ?wiki...",
            "Why did the bot use ?wiki at the comedy club? It wanted to look up punchlines!",
            "I'd tell you to RTFM, but just use ?wiki instead.",
            "I had a joke about ?wiki, but I need to look it up."
        ]

        if hasattr(self, 'last_joke') and self.last_joke:
            joke_responses.remove(self.last_joke)

        random_joke = random.choice(joke_responses)
        self.last_joke = random_joke

        if username in self.whitelist:
            response = "Available functions: ?wiki, ?add, ?remove, ?keys, ?axe"
            self.send_response(response)
        else:
            self.send_response(random_joke)

    @whitelist_check
    @log_command
    def wikiadd(self, *args):
        """
        Adds a new shortcut for the wiki command. Requires a key:value format.
        """
        new_shortcut = args[1].lower()
        if ":" not in new_shortcut:
            add_error = "Expected key:value, item not added"
            self.send_response(add_error)
            return

        new_key, new_item = new_shortcut.split(":")

        if new_key == "zlef":
            self.send_response("Zlef has been added as a shortcut for awesome")
            return
        elif new_key == "cammy":
            self.send_response(f"{new_key} has been added as a shortcut for {new_item}")
            return

        if new_key in self.shortcuts:
            message = f"That key is already in use for {self.shortcuts[new_key]}. Use ?keys to view the err... Keys..."
            self.send_response(message)
            return

        self.shortcuts[new_key] = new_item
        self.save_configs()
        self.send_response(f"{new_key} has been added as a shortcut for {new_item}")

    @whitelist_check
    @log_command
    def wikiremove(self, *args):
        """
        Removes an existing shortcut from the wiki command list.
        """
        key_to_remove = args[1].lower()
        if key_to_remove not in self.shortcuts:
            self.send_response(f"The key {key_to_remove} doesn't exist. Nothing to remove.")
            return
        if key_to_remove == "cammy":
            self.send_response(f"{key_to_remove} has been removed.")
            return

        del self.shortcuts[key_to_remove]
        self.save_configs()
        confirmation = f"{key_to_remove} has been removed."
        self.send_response(confirmation)

    @whitelist_check
    @log_command
    def wikikeys(self, *args):
        """
        Lists all current shortcut keys for the wiki command, with support for pagination.
        """
        command_arg = args[1].lower()
        total_keys = sorted(self.shortcuts.keys())
        total_keys_string = ", ".join(total_keys)
        max_chars = 240
        prefix = "Keys page "
        max_message_length = max_chars - len(prefix)

        total_pages = -(-len(total_keys_string) // max_message_length)  # Use ceiling division

        message_parts = command_arg
        if len(message_parts) > 1 and message_parts[1].isdigit():
            page_requested = int(message_parts[1])
        else:
            page_requested = 0

        if page_requested == 0:
            if total_pages == 1:
                page_requested = 1  # Set to first page if there's only one
            else:
                page_message = f'Use "?keys n" to specify a page. Currently, there are {total_pages} pages.'
                self.send_response(page_message)
                return

        page_requested = min(page_requested, total_pages)

        start_idx = (page_requested - 1) * max_message_length
        end_idx = start_idx + max_message_length

        response_keys = total_keys_string[start_idx:end_idx]

        if total_pages == 1:
            response_message = f"{prefix} of 1: {response_keys}"
        else:
            response_message = f"{prefix}{page_requested} of {total_pages}: {response_keys}"

        self.send_response(response_message)

    @whitelist_check
    @log_command
    def wikiaxe(self, *args):
        """
        Sends a random joke related to the 'Axe' character, avoiding repetition.
        """
        axe_jokes = [
            "Axe is level 15 because otherwise he'd be too ostentatious and you wouldn't be able to play what with all the bowing and scraping",
             "Shhhh, Lux is undercover as Axe to hide his moderator tag.",
             "Now you've done it! Years of undercover work blown because you just had to know why the moderator has an alt account.",
             "Axe at level 15 is like Bruce Wayne in a tracksuit—still dangerous but less showy.",
             "Why does Axe stay at level 15? So he doesn't have to put 'Incognito Mode' in his username.",
             "Smitty once tried to upgrade Axe to level 16, but the universe crashed. Took him a week to restore the balance."
        ]
        chosen_joke = random.choice(axe_jokes)
        while chosen_joke == self.last_axe_joke:
            chosen_joke = random.choice(axe_jokes)
        self.last_axe_joke = chosen_joke
        self.send_response(chosen_joke)

    @whitelist_check
    @log_command
    def wikisay(self, *args):
        """
        Echoes back the given argument.
        """
        command_arg = args[1]
        print(command_arg)
        self.send_response(command_arg)

    @cooldown
    @log_command
    def wikizombo(self, *args):
        """
        Echoes back the given argument.
        """
        username = args[0]
        command_args = args[1]
        print(f"username: {username}, args: {command_args}")
        if username == "godofnades" and "stop" in command_args:
            self.nades = True
            self.send_response("Command disabled! Note this will reset on next launch if not removed")
        if not self.nades:
            self.send_response("BotofNades is experiencing an oopsy. The -Green Zombie- is in Forest. To disable this GodofNades, send '!zombo stop' and remind me to take this out")
        print(self.nades)


    @whitelist_check
    @log_command
    def wikicustom(self, *args):
        """
        Echoes back the given argument.
        """
        command_arg = args[1]
        # self.send_response(command_arg)

        # self.socket_handler.ws.send(f"CUSTOM={args[1]}")
        self.socket_handler.ws.send("CUSTOM=botofnades~altTrader:info:ping")

    @whitelist_check
    @log_command
    def wadd(self, *args):
        """
        Adds a user to the whitelist, exclusive to 'zlef'.
        """
        username = args[0]
        if username == "zlef":
            command_arg = args[1]
            self.whitelist.append(command_arg)
            self.save_configs()
            self.send_response(f"{command_arg} added to whitelist")

    @whitelist_check
    @log_command
    def wremove(self, *args):
        """
        Removes a user from the whitelist, exclusive to 'zlef'.
        """
        username = args[0]
        if username == "zlef":
            command_arg = args[1]
            self.whitelist.remove(command_arg)
            self.save_configs()
            self.send_response(f"{command_arg} removed from whitelist")

    @whitelist_check
    @log_command
    def badd(self, *args):
        """
        Adds a user to the blacklist.
        """
        command_arg = args[1]
        self.blacklist.append(command_arg)
        self.save_configs()
        self.send_response(f"{command_arg} added to blacklist")

    @whitelist_check
    @log_command
    def bremove(self, *args):
        """
        Removes a user from the blacklist.
        """
        command_arg = args[1]
        self.blacklist.remove(command_arg)
        self.save_configs()
        self.send_response(f"{command_arg} removed from blacklist")

    @whitelist_check
    @log_command
    def wikiwoof(self, *args):
        """
        Responds to "wikisearch is a good boy" with "Woof!"
        """
        self.send_response("Woof!")

    def start(self):
        self.socket_handler.initialize_websocket()


if __name__ == "__main__":
    '''
    TODO:
    '''
    # bot = WikiBot("testzlef", "zleftest92")
    bot = WikiBot()
    bot.start()


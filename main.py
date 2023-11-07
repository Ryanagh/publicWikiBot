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


class WebSocketHandler:
    def __init__(self, on_chat, username, password):
        self.on_chat = on_chat
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
            raw_split = message.replace("CHAT=", "").split("~")
            player_details = {
                "username": raw_split[0],
                "sigil": raw_split[1],
                "tag": raw_split[2],
                "level": raw_split[3],
            }
            player_message = raw_split[4]
            username = player_details["username"]
            self.on_chat([username, player_message])
        elif "CUSTOM=" in message:
            msg_split = message.replace("CUSTOM=", "").split("~")
            username = msg_split[0].lower()
            if "interactor" in message:
                command = "interactor?" + message.split("interactor")[1].lstrip(":").lower()
                self.on_chat([username, command])
        elif "SET_ITEMS=" in message:
            pass
        elif "YELL=" in message:
            pass
        elif "EVENT_GLOBAL_PROGRESS=" in message:
            pass
        else:
            print(message)

    def on_ws_error(self, ws, error):
        print(f"WebSocket error: {error}")

    def on_ws_close(self, ws, close_status_code, close_msg):
        print("WebSocket closed.")


class WikiBot:
    COOLDOWN_TIME = 60  # cooldown in seconds (1 minute)

    def __init__(self, username, password):
        self.socket_handler = WebSocketHandler(self.on_chat, username, password)
        self.debug = True
        self.force_local = False
        self.testing = False
        self.load_config()
        self._last_called = 0
        self.last_axe_joke = ""
        self.lastRunDict = {}
        self.jokes = True
        self.fakename = "notzlef"
        self.callbackID = 1 # This should probably be saved outside the bot, oh well

        print(f"Debug: {self.debug} || Testing (replaces zlef with {self.fakename}): {self.testing}")

    def cooldown(func):
        def wrapper(self, username, *args, **kwargs):
            current_time = time.time()
            if username in self.blacklist or "austin" in username:
                self.send_response(f"Blacklisted user {username} attempted to trigger a command", True)
            else:
                if username in self.whitelist:
                    return func(self, username, *args, **kwargs)
                if self.lastRunDict.get(func.__name__, 0) + WikiBot.COOLDOWN_TIME <= current_time:
                    self.lastRunDict[func.__name__] = current_time
                    return func(self, username, *args, **kwargs)
                else:
                    self.send_response(f"{username} attempted to call {func.__name__} while on cooldown", True)
        return wrapper

    def load_config(self):
        with open("config.json", "r") as f:
            config = json.load(f)
            self.blacklist = config["blacklist"]
            self.whitelist = config["whitelist"]
            self.alttraderlist = config["alttraderlist"]
            self.profanitylist = config["profanitylist"]
            self.shortcuts = config["shortcuts"]

    def save_configs(self):
        with open("config.json", "w") as f:
            config = {
                "blacklist": self.blacklist,
                "whitelist": self.whitelist,
                "alttraderlist": self.alttraderlist,
                "profanitylist": self.profanitylist,
                "shortcuts": self.shortcuts
            }
            json.dump(config, f, indent=4)

    def send_response(self, message, force_debug=False):
        if self.debug or force_debug:
            if not self.force_local:
                self.socket_handler.ws.send(f"CUSTOM=zlef~WIKI{self.callbackID}:wikibot:{message}")
                self.callbackID += 1
            else:
                print(message)
        else:
            self.socket_handler.ws.send(f"CHAT={message}")

    def debug_handler(self, username, debug_txt, try_on_chat=True):
        print(f"{username}: {debug_txt}")
        if "interactor" not in debug_txt:
            debug_txt = "interactor" + debug_txt.replace(" ", ":")
            # Super lazy work around to make debug command work on chat
        debug_command = debug_txt.split("?")[1].split(":")
        command = debug_command[0]
        try:
            command_value = debug_command[1].strip()
        except:
            command_value = ""
        # print(f"debug handler received {command} with value {value}")
        if command == "help":
            debug_commands = ["debug", "testing", "name", "jokes", "local"]
        elif command == "debug":
            if command_value == "true":
                self.debug = True
            elif command_value == "false":
                self.debug = False
            else:
                self.send_response(f"Failed to set debug value, expects \"true\" or \"false\", received {command_value}", True)
                return
            self.send_response(f"self.debug set to {self.debug}. When True all responses will be via CUSTOM as opposed to CHAT", True)
        elif command == "testing":
            if command_value == "true":
                self.testing = True
            elif command_value == "false":
                self.testing = False
            else:
                self.send_response(f"Failed to set testing value, expects \"true\" or \"false\", received {command_value}", True)
            self.send_response(f"self.testing set to {self.testing}. When True all functions will receive {self.fakename} instead of user in whitelist. Set with command 'name'.", True)
        elif command == "name":
            self.fakename = command_value
            self.send_response(f"self.fakename set to {self.fakename}. Set Testing to true to use.", True)
        elif command == "jokes":
            if command_value == "true":
                self.jokes = True
            elif command_value == "false":
                self.jokes = False
            else:
                self.send_response(f"Failed to set jokes value, expects \"true\" or \"false\", received {command_value}", True)
                return
            self.send_response(f"self.jokes set to {self.debug}. When True there is a chance of jokes for set users", True)
        elif command == "local":
            if command_value == "true":
                self.force_local = True
            elif command_value == "false":
                self.force_local = False
            else:
                self.send_response(f"Failed to set force_local value, expects \"true\" or \"false\", received {command_value}", True)
            self.send_response(f"self.force_local set to {self.force_local}. When True all CUSTOM response will print locally instead of returning via CUSTOM", True)
        else:
            chat_command = f"?{command} {command_value}"
            if try_on_chat:
                self.on_chat([username, chat_command])

        # elif debug_command == "vars":
        #     for attr_name, attr_value in self.__dict__.items():
        #         self.send_response(f"class.{attr_name} is {attr_value}", True)


    def on_chat(self, message):
        # print(f"Received chat message: {message}")
        username = message[0]
        if self.testing and username in self.whitelist:
            username = self.fakename
        contents = message[1].lower()
        if username not in self.blacklist:
            if contents.startswith("?wiki"):
                self.wikiurl(username, contents)
            elif contents.startswith("?help"):
                self.wikihelp(username, contents)
            elif contents.startswith("?add"):
                self.wikiadd(username, contents)
            elif contents.startswith("?remove"):
                self.wikiremove(username, contents)
            elif contents.startswith("?keys"):
                self.wikikeys(username, contents)
            elif contents.startswith("?axe"):
                self.wikiaxe(username, contents)
            elif contents.startswith("?say") and username in self.whitelist:
                self.send_response(contents.lstrip("?say "))
            elif contents.startswith("interactor") or contents.startswith("?debug"):
                if username in self.whitelist or username == self.fakename:
                    self.debug_handler(username, contents, False)

    @cooldown
    def wikiurl(self, username, player_message):
        if username in self.alttraderlist:
            self.send_response("I think this is the link you're looking for: https://idle-pixel.com/rules/ (under alt trading)")
            self.send_response(f"{username} triggered alt trader response @ {datetime.now().strftime('%c')}", True)
            return

        if player_message.strip() == "?wiki":
            self.send_response(f"Use ?wiki <search term>. Cooldown applied, try again in {WikiBot.COOLDOWN_TIME} seconds")
            return

        message_parts = player_message.split(" ")
        message_parts.pop(0)
        search_term = " ".join(message_parts).split("@")[0].strip()

        # Profanity check start
        search_term_words = search_term.lower().split(' ')
        contains_bad_word = any(bad_word in search_term_words for bad_word in self.profanitylist)

        if contains_bad_word:
            self.send_response(f"Profanity detected from {username} at {datetime.now().strftime('%c')}", True)
            return
        # Profanity check end

        if search_term.lower() == "hi":
            self.send_response("I'm not ChatGPT, I won't pretend to be your girlfriend.")
            self.send_response(f"{username} said hi at {datetime.now().strftime('%c')}", True)
            return

        search_term = urllib.parse.quote(search_term)
        if search_term in self.shortcuts:
            search_term = urllib.parse.quote(self.shortcuts[search_term])
        wiki_link = f"https://idle-pixel.wiki/index.php?search={search_term}"

        joke_lists = {"cammyrock": ["Who's a good girl!", ""]} # Removed from public... Mostly

        joke_for_user = joke_lists.get(username)
        if joke_for_user and self.jokes and (random.randint(1, 20) == 1 or username == "fwash"):
            if hasattr(self, 'last_user_joke') and self.last_user_joke.get(username):
                joke_for_user = [j for j in joke_for_user if j != self.last_user_joke[username]]

            joke = random.choice(joke_for_user)
            if not hasattr(self, 'last_user_joke'):
                self.last_user_joke = {}
            self.last_user_joke[username] = joke

            self.send_response(f"{joke} {wiki_link}")
            self.send_response(f"{username} triggered a joke with {urllib.parse.unquote(search_term)} at {datetime.now().strftime('%c')}",True)
        else:
            self.send_response(wiki_link)
            self.send_response(f"{username} triggered {urllib.parse.unquote(search_term)} at {datetime.now().strftime('%c')}", False)

    @cooldown
    def wikihelp(self, username, player_message):

        self.send_response(f"{username} triggered wikihelp at {datetime.now().strftime('%c')}", True)

        joke_responses = ["", ""] # Removed from public

        if hasattr(self, 'last_joke') and self.last_joke:
            joke_responses.remove(self.last_joke)

        random_joke = random.choice(joke_responses)
        self.last_joke = random_joke

        if username in self.whitelist:
            response = "Available functions: ?wiki, ?add, ?remove, ?keys, ?axe"
            self.send_response(response)
        else:
            self.send_response(random_joke)

    def wikiadd(self, username, player_message):
        self.send_response(f"{username} triggered wikiadd with conditions {player_message} at {datetime.now().strftime('%c')}", True)

        if username in self.whitelist:
            message_parts = player_message.split(" ")
            message_parts.pop(0)
            new_shortcut = " ".join(message_parts).lower()

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
            self.send_response(f"{new_key} has been added as a shortcut")

    def wikiremove(self, username, player_message):
        if username in self.whitelist:
            self.send_response(f"{username} triggered wikiremove with conditions {player_message} at {datetime.now().strftime('%c')}", True)
            message_parts = player_message.split(" ")
            message_parts.pop(0)
            key_to_remove = " ".join(message_parts).lower()

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
        else:
            self.send_response(f"{username} tried to trigger wikiremove with conditions {player_message} at {datetime.now().strftime('%c')}", True)

    def wikikeys(self, username, player_message):
        self.send_response(f"{username} triggered wikikeys with conditions {player_message} at {datetime.now().strftime('%c')}", True)

        if username in self.whitelist:
            total_keys = sorted(self.shortcuts.keys())
            total_keys_string = ", ".join(total_keys)
            max_chars = 240
            prefix = "Keys page "
            max_message_length = max_chars - len(prefix)

            total_pages = -(-len(total_keys_string) // max_message_length)  # Use ceiling division

            message_parts = player_message.split(" ")
            if len(message_parts) > 1 and message_parts[1].isdigit():
                page_requested = int(message_parts[1])
            else:
                page_requested = 0

            # Modify the condition here:
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

    def wikiaxe(self, username, player_message):
        if username in self.whitelist:
            axe_jokes = ["",""] # Removed from public
            chosen_joke = random.choice(axe_jokes)
            while chosen_joke == self.last_axe_joke:
                chosen_joke = random.choice(axe_jokes)
            self.last_axe_joke = chosen_joke
            self.send_response(chosen_joke)

    def wikisay(self, username, player_message):
        if username in self.whitelist:
            self.send_response(player_message)

    def start(self):
        self.socket_handler.initialize_websocket()


if __name__ == "__main__":
    '''
    Handle auto log on update  
    '''
    username = ""
    password = ""
    bot = WikiBot(username, password)
    bot.start()


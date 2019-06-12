# Async chat with GUI
GUI  async chat with registration
# How to install
Python version required: 3.7+
1. Recomended use venv or virtualenv for better isolation.\
   Venv setup example: \
   `python3 -m venv myenv`\
   `source myenv/bin/activate`
2. Install requirements: \
   `pip3 install -r requirements.txt` (alternatively try add `sudo` before command)
3. `cp env/.env env/.env_file`. If it need setup `env/.env_file` (or use default settings):
        - `HOST` - chat host. \
        - `READ_PORT` - port for read messages from chat. \
        - `SEND_PORT` - port for write messages to chat. \
        - `ATTEMPTS_COUNT` - connection attempts before 3 sec timeout.  \
        - `HISTORY_LOG_DIR_PATH` - path to folder where will be created `history_log.txt` file with chat messages history. \
        - `TOKEN_FILE_PATH` - path to file with unique user token(by default - `./token.txt`)\
  
# How to launch
Instead environ vars you can use arguments. For more info use `python3 chat_register.py --help` (for register) and `python3 gui_chat.py --help` (for chat) \
For using environ vars you need `source env/.env_file`.
1. If you want registered:
   1) Run `python3 chat_register.py`. 
   2) Enter desired nickname. If all ok token will be saved in token file.
2. If you are already registered or don't want register:
   1) For signin token is required. You can set it in `env/.env_file` or use argument or load from file(
   uses argument too or default `./token.txt.`).  
   2) Run `python3 gui_chat.py`


# Project Goals
The code is written for educational purposes. Training course for web-developers - [DVMN.org](https://dvmn.org)

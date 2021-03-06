#!/usr/bin/env python

import os
import argparse
import json

from re import sub
from random import shuffle, randint
from simpleconfigparser import simpleconfigparser
from datetime import datetime, timedelta

import praw
from praw.errors import InvalidUser, InvalidUserPass, RateLimitExceeded, \
                        HTTPException, OAuthAppRequired
from praw.objects import Comment, Submission

try:
    from loremipsum import get_sentence  # This only works on Python 2
except ImportError:
    def get_sentence():
        return '''I have been Shreddited for privacy!'''
    os_wordlist = '/usr/share/dict/words'
    if os.name == 'posix' and os.path.isfile(os_wordlist):
        # Generate a random string of words from our system's dictionary
        fh = open(os_wordlist)
        words = fh.read().splitlines()
        fh.close()
        shuffle(words)
        def get_sentence():
            return ' '.join(words[:randint(50, 150)])

assert get_sentence

parser = argparse.ArgumentParser()
parser.add_argument(
    '-c',
    '--config',
    help="config file to use instead of the default shreddit.cfg"
)
args = parser.parse_args()

config = simpleconfigparser()
if args.config:
    config.read(args.config)
else:
    config.read('shreddit.cfg')

hours = config.getint('main', 'hours')
whitelist = config.get('main', 'whitelist')
whitelist_ids = config.get('main', 'whitelist_ids')
sort = config.get('main', 'sort')
verbose = config.getboolean('main', 'verbose')
clear_vote = config.getboolean('main', 'clear_vote')
trial_run = config.getboolean('main', 'trial_run')
edit_only = config.getboolean('main', 'edit_only')
item = config.get('main', 'item')
whitelist_distinguished = config.getboolean('main', 'whitelist_distinguished')
whitelist_gilded = config.getboolean('main', 'whitelist_gilded')
nuke_hours = config.getint('main', 'nuke_hours')
try:
    max_score = config.getint('main', 'max_score')
except ValueError:
    max_score = None
except TypeError:
    max_score = None
save_directory = config.get('main', 'save_directory')

_user = config.get('main', 'username')
_pass = config.get('main', 'password')

r = praw.Reddit(user_agent="shreddit/4.0")
if save_directory:
    r.config.store_json_result = True

def login(user=None, password=None):
    try:
        # This is OAuth 2
        r.refresh_access_information()
        if verbose:
            print("Logged in with OAuth.")
    except (HTTPException, OAuthAppRequired) as e:
        try:
            if user and password:
                r.login(_user, _pass)
            else:
                r.login()  # Let the user supply details
        except InvalidUser as e:
            raise InvalidUser("User does not exist.", e)
        except InvalidUserPass as e:
            raise InvalidUserPass("Specified an incorrect password.", e)
        except RateLimitExceeded as e:
            raise RateLimitExceeded("You're doing that too much.", e)

if not r.is_logged_in():
    login(user=_user, password=_pass)

if verbose:
    print("Logged in as {user}.".format(user=r.user))

if verbose:
    print("Deleting messages before {time}.".format(
        time=datetime.now() - timedelta(hours=hours))
    )

whitelist = [y.strip().lower() for y in whitelist.split(',')]
whitelist_ids = [y.strip().lower() for y in whitelist_ids.split(',')]

if verbose and whitelist:
    print("Keeping messages from subreddits {subs}".format(
        subs=', '.join(whitelist))
    )

def get_things(after=None):
    limit = None 
    if item == "comments":
        return r.user.get_comments(limit=limit, sort=sort)
    elif item == "submitted":
        return r.user.get_submitted(limit=limit, sort=sort)
    elif item == "overview":
        return r.user.get_overview(limit=limit, sort=sort)
    else:
        raise Exception("Your deletion section is wrong")

def remove_things(things):
    removal_count = 0
    for thing in things:
        # Seems to be in users's timezone. Unclear.
        thing_time = datetime.fromtimestamp(thing.created_utc)
        # Exclude items from being deleted unless past X hours.
        after_time = datetime.now() - timedelta(hours=hours)
        if thing_time > after_time:
            if thing_time + timedelta(hours=nuke_hours) < datetime.utcnow():
                pass
            continue
        # For edit_only we're assuming that the hours aren't altered.
        # This saves time when deleting (you don't edit already edited posts).
        if edit_only:
            end_time = after_time - timedelta(hours=hours)
            if thing_time < end_time:
                    continue

        if str(thing.subreddit).lower() in whitelist or \
           thing.id in whitelist_ids:
            continue

        if whitelist_distinguished and thing.distinguished:
            continue
        if whitelist_gilded and thing.gilded:
            continue
        if max_score is not None and thing.score > max_score:
            continue

        if trial_run:  # Don't do anything, trial mode!
            if verbose:
                content = thing
                content = str(content).encode('ascii', 'ignore')
                print("Would have deleted {thing}: '{content}'".format(
                    thing=thing.id, content=thing))
            continue

        if save_directory:
            if not os.path.exists(save_directory):
                os.makedirs(save_directory)
            with open("%s/%s.json" % (save_directory, thing.id), "w") as fh:
                json.dump(thing.json_dict, fh)

        if clear_vote:
            thing.clear_vote()

        if isinstance(thing, Submission):
            if verbose:
                print('Deleting submission: #{id} {url}'.format(
                    id=thing.id,
                    url=thing.url.encode('utf-8'))
                )
        elif isinstance(thing, Comment):
            replacement_text = get_sentence()
            if verbose:
                msg = '/r/{3}/ #{0} with:\n\t"{1}" to\n\t"{2}"'.format(
                    thing.id,
                    sub(b'\n\r\t', ' ', thing.body[:78].encode('utf-8')),
                    replacement_text[:78],
                    thing.subreddit
                )
                if edit_only:
                    print('Editing {msg}'.format(msg=msg))
                else:
                    print('Editing and deleting {msg}'.format(msg=msg))

            thing.edit(replacement_text)
            removal_count += 1  # rename?  this includes edits as well as deletions
        if not edit_only:
            thing.delete()
            removal_count += 1
    return removal_count

things = get_things()
count = remove_things(things)
while count != 0:
    things = get_things()
    count = remove_things(things)


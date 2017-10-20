# Copyright 2016 Mycroft AI, Inc.
#
# This file is part of Mycroft Core.
#
# Mycroft Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Mycroft Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Mycroft Core.  If not, see <http://www.gnu.org/licenses/>.

import time
import yaml
from alsaaudio import Mixer
from datetime import datetime, timedelta
from os.path import dirname, join

from mycroft import MycroftSkill
from mycroft.util import play_mp3

from difflib import SequenceMatcher
import re
from abc import ABCMeta, abstractmethod
from datetime import datetime

from enum import Enum, unique

from mycroft.util.log import LOG


@unique
class TimeType(Enum):
    SEC = 1
    MIN = SEC * 60
    HR = MIN * 60
    DAY = HR * 24

    def to_sec(self, amount):
        return amount * self.value

    def from_sec(self, num_sec):
        return num_sec / self.value


class MycroftParser(object):
    __metaclass__ = ABCMeta
    """Helper class to parse common parameters like duration out of strings"""
    def __init__(self):
        pass

    @abstractmethod
    def format_quantities(self, quantities):
        """
        Arranges list of tuples of (ttype, amount) into language
        [(MIN, 12), (SEC, 3)] -> '12 minutes and three seconds'
        Args:
            quantities(list<tuple<TimeType, int>>):

        Returns:
            str: quantities in natural language
        """
        pass

    @abstractmethod
    def duration(self, string):
        """
        Raises: ValueError, if nothing found

        Returns:
            tuple<float, float>: duration in natural language string in seconds, confidence [0, 1]
        """
        pass

    @abstractmethod
    def to_number(self, string):
        """
        Converts word numbers to digit numbers
        Example: 'fifty 3 lemons and 2 hundred carrots' -> '53 lemons and '

        Returns:
            tuple<float, float>: converted number, confidence [0, 1]
        """
        pass

    def duration_to_str(self, dur):
        """
        Converts duration in seconds to appropriate time format in natural langauge
        70 -> '1 minute and 10 seconds'
        """
        quantities = []
        left_amount = dur
        for ttype in reversed(list(TimeType)):
            amount = ttype.from_sec(left_amount)
            int_amount = int(amount + 0.000000001)
            left_amount = ttype.to_sec(amount - int_amount)
            if int_amount > 0:
                quantities.append((ttype, int_amount))
        return self.format_quantities(quantities)


class Parser(MycroftParser):
    """Helper class to parse common parameters like duration out of strings"""

    def __init__(self):
        self.units = [
            ('one', '1'),
            ('two', '2'),
            ('three', '3'),
            ('four', '4'),
            ('five', '5'),
            ('size', '6'),
            ('seven', '7'),
            ('eight', '8'),
            ('nine', '9'),
            ('ten', '10'),
            ('eleven', '11'),
            ('twelve', '12'),
            ('thir', '3.'),
            ('for', '4.'),
            ('fif', '5.'),
            ('teen', '+10'),
            ('ty', '*10'),
            ('hundred', '* 100'),
            ('thousand', '* 1000'),
            ('million', '* 1000000'),
            ('and', '_+_')
        ]
        self.ttype_names_s = {
            TimeType.SEC: ['second', 'sec', 's'],
            TimeType.MIN: ['minute', 'min', 'm'],
            TimeType.HR: ['hour', 'hr', 'h'],
            TimeType.DAY: ['day', 'dy', 'd']
        }

        self.day_numbers = {
            'today': 0,
            'tomorrow': 1,
        }
        self.week_days = {
            'monday',
            'tuesday',
            'wednesday',
            'thursday',
            'friday',
            'saturday',
            'sunday'
        }

        units = [
            "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
            "sixteen", "seventeen", "eighteen", "nineteen",
        ]

        tens = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
                "ninety"]

        scales = ["hundred", "thousand", "million", "billion", "trillion"]

        self.numwords = {}
        self.numwords["and"] = (1, 0)
        for idx, word in enumerate(units):
            self.numwords[word] = (1, idx)
        for idx, word in enumerate(tens):
            self.numwords[word] = (1, idx * 10)
        for idx, word in enumerate(scales):
            self.numwords[word] = (10 ** (idx * 3 or 2), 0)

    def duration(self, string):
        regex_str = ('(((' + '|'.join(k for k, v in self.units) + r'|[0-9])+[ \-\t]*)+)(' +
                     '|'.join(name for ttype, names in self.ttype_names_s.items() for name in
                              names) + ')s?')
        dur, conf = 0, 0.0
        matches = tuple(re.finditer(regex_str, string))
        if len(matches) == 0:
            raise ValueError
        for m in matches:
            num_str = m.group(1)
            ttype_str = m.group(4)
            for ttype, names in self.ttype_names_s.items():
                if ttype_str in names:
                    ttype_typ = ttype
            num, conf = self.to_number(num_str)
            dur += ttype_typ.to_sec(num)
        return dur, conf

    def time(self, time_str, morning=False, evening=False):
        LOG.info('TIME')
        if 'am' in time_str.lower():
            morning = True
        if 'pm' in time_str.lower():
            evening = True
        LOG.info(time_str)
        m = re.search('[0-9]{1,2}:[0-9]{2}', time_str)
        LOG.info(m)
        if m:
            match = m.group(0)
            hour, minute = match.split(':')
        else:
            m = re.search('[0-9]{0,2}', time_str)
            if m:
                match = m.group(0)
                hour, minute = match, '0'
            else:
                raise ValueError
        now = datetime.now()
        day, hour, minute = 0, int(hour), int(minute)
        LOG.info('HOUR:' + str(hour))
        LOG.info(str(hour) + ":" + str(minute))
        if evening:
            hour += 12
        dh = hour - now.hour
        if dh < 0:
            hour += 24
        if not evening and not morning:
            dh = hour - now.hour
            LOG.info('DH:' + str(dh))
            if dh > 6:
                hour -= 12

        elif dh == 0:
            dm = minute - now.minute
            if dm < 0:
                hour += 24

        if hour >= 24:
            day += 1
            hour -= 24
        LOG.info(hour)

        time_str = time_str.replace(match, '')
        return time_str, datetime(now.year, now.month, now.day + day, hour, minute)

    def days(self, time_str):
        for day in self.day_numbers:
            if day in time_str:
                day = self.day_numbers[day] + datetime.today().day
                return time_str.replace(day, ''), datetime(0, 0, day)

        now = datetime.now()
        yr, mo = now.year, now.month
        for day in self.week_days:
            if day in time_str:
                today = datetime.today().weekday()
                duration = self.week_days.index(day) - today
                if duration < 0:
                    duration += len(self.week_days)
                day = datetime.today().day + duration
                return time_str.replace(day, ''), datetime(yr, mo, day)
        return time_str, datetime(yr, mo, datetime.today().day)

    def date(self, time_str, morning=False, evening=False):
        time_str, day = self.days(time_str)
        time_str, time = self.time(time_str, morning, evening)
        t = datetime.now()
        t = datetime(t.year, t.month, day.day, time.hour, time.minute)
        return time_str, t

    def to_number(self, textnum):

        ordinal_words = {'first': 1, 'second': 2, 'third': 3, 'fifth': 5, 'eighth': 8,
                         'ninth': 9, 'twelfth': 12}
        ordinal_endings = [('ieth', 'y'), ('th', '')]

        textnum = textnum.replace('-', ' ')

        current = result = 0
        curstring = ""
        onnumber = False
        for word in textnum.split():
            if word in ordinal_words:
                scale, increment = (1, ordinal_words[word])
                current = current * scale + increment
                if scale > 100:
                    result += current
                    current = 0
                onnumber = True
            else:
                for ending, replacement in ordinal_endings:
                    if word.endswith(ending):
                        word = "%s%s" % (word[:-len(ending)], replacement)
                try:
                    num = float(word)
                    if num % 1 == 0:
                        num = int(num)
                except ValueError:
                    num = None

                if word not in self.numwords and num is None:
                    if onnumber:
                        curstring += repr(result + current) + " "
                    curstring += word + " "
                    result = current = 0
                    onnumber = False
                else:
                    if num is not None:
                        scale, increment = 1, num
                    else:
                        scale, increment = self.numwords[word]

                    current = current * scale + increment
                    if scale > 100:
                        result += current
                        current = 0
                    onnumber = True
            if onnumber:
                curstring += repr(result + current)
            return curstring

    def to_number(self, string):
        string = string.replace('-', ' ')  # forty-two -> forty two
        for unit, value in self.units:
            string = string.replace(unit, value)
        string = re.sub(r'([0-9]+)[ \t]*([\-+*/])[ \t]*([0-9+])', r'\1\2\3', string)

        regex_re = [
            (r'[0-9]+\.([^\-+*/])', r'a\1'),
            (r'\.([\-+*/])', r'\1'),
            (r' \* ', r'*'),
            (r' _\+_ ', r'+'),
            (r'([^0-9])\+[0-9]+', r'\1'),
            (r'([0-9]) ([0-9])', r'\1+\2'),
            (r'(^|[^0-9])[ \t]*[\-+*/][ \t]*', ''),
            (r'[ \t]*[\-+*/][ \t]*([^0-9]|$)', '')
        ]

        for sr, replace in regex_re:
            string = re.sub(sr, replace, string)

        num_strs = re.findall(r'[0-9\-+*/]+', string)
        if len(num_strs) == 0:
            raise ValueError

        num_str = max(num_strs, key=len)

        conf = SequenceMatcher(None, string.replace(' ', ''), num_str.replace(' ', '')).ratio()

        try:
            # WARNING Eval is evil; always filter string to only numbers and operators
            return eval(num_str), conf
        except SyntaxError:
            raise ValueError

    def format_quantities(self, quantities):
        complete_str = ', '.join(
            [str(amount) + ' ' + self.ttype_names_s[ttype][0] + ('s' if amount > 1 else '') for
             ttype, amount in quantities])
        complete_str = ' and '.join(complete_str.rsplit(', ', 1))
        return complete_str


class AlarmSkill(MycroftSkill):

    def __init__(self):
        super(AlarmSkill, self).__init__()
        self.alarm_on = False
        self.max_delay = self.config['max_delay']
        self.repeat_time = self.config['repeat_time']
        self.extended_delay = self.config['extended_delay']
        self.file_path = join(dirname(__file__), self.config['filename'])
        self.parser = Parser()

    def initialize(self):
        self.register_intent_file('stop.intent', self.__handle_stop)
        self.register_intent_file('set.morning.intent', self.set_morning)
        self.register_intent_file('set.sunrise.intent', self.set_sunrise)
        self.register_intent_file('set.recurring.intent', self.set_recurring)
        self.register_intent_file('stop.intent', self.stop)
        self.register_intent_file('set.time.intent', self.set_time)
        self.register_intent_file('delete.all.intent', self.delete_all)
        self.register_intent_file('delete.intent', self.delete)
        self.register_entity_file('time.entity')
        self.register_entity_file('length.entity')
        self.register_entity_file('daytype.entity')
        self.register_entity_file('exceptdaytype.entity')

    def create_in_delta_seconds(self, seconds):
        hours, seconds = divmod(seconds, 60 * 60)
        minutes = seconds / 60
        data = {
            'hours': hours,
            'minutes': minutes
        }

        hm = ''
        if hours > 0:
            hm += 'h'
        if minutes > 0:
            hm += 'm'
        if hm == '':
            hm = 'm'

        self.speak_dialog('alarm.set.' + hm, data=data)

    def set_for_length(self, dur_str):
        seconds, conf = self.parser.duration(dur_str)
        self.create_in_delta_seconds(seconds)

    def set_for_time(self, time_str, morning=False, evening=False):
        time_str, dt = self.parser.date(time_str, morning, evening)
        self.create_in_delta_seconds((dt - datetime.now()).seconds)

    def set_time(self, message):
        try:
            if 'time' in message.data:
                return self.set_for_time(message.data['time'])
            elif 'length' in message.data:
                return self.set_for_length(message.data['length'])
        except ValueError:
            pass
        self.speak_dialog('no.time.found')

    def set_morning(self, message):
        try:
            if 'time' in message.data:
                return self.set_for_time(message.data['time'], morning=True)
            elif 'length' in message.data:
                return self.set_for_length(message.data['length'])
        except ValueError:
            pass
        self.speak_dialog('no.time.found')

    def set_sunrise(self, message):
        pass

    def set_recurring(self, message):
        pass

    def delete_all(self, message):
        pass

    def delete(self, message):
        pass

    def load_data(self):
        try:
            with self.file_system.open(self.PENDING_TASK, 'r') as f:
                self.data = yaml.safe_load(f)
            if not self.data:
                raise ValueError
        except:
            self.data = {}

    def load_repeat_data(self):
        try:
            with self.file_system.open(self.REPEAT_TASK, 'r') as f:
                self.repeat_data = yaml.safe_load(f)
                assert self.repeat_data
        except:
            self.repeat_data = {}

    def __handle_stop(self, message):
        if self.alarm_on:
            self.speak_dialog('alarm.off')
        self.alarm_on = False

    def notify(self, timestamp):
        with self.LOCK:
            if self.data.__contains__(timestamp):
                volume = None
                self.alarm_on = True
                delay = self.__calculate_delay(self.max_delay)

                while self.alarm_on and datetime.now() < delay:
                    play_mp3(self.file_path).communicate()
                    self.speak_dialog('alarm.stop')
                    time.sleep(self.repeat_time + 2)
                    if not volume and datetime.now() >= delay:
                        mixer = Mixer()
                        volume = mixer.getvolume()[0]
                        mixer.setvolume(100)
                        delay = self.__calculate_delay(self.extended_delay)
                if volume:
                    Mixer().setvolume(volume)
                self.remove(timestamp)
                self.alarm_on = False
                self.save()

    @staticmethod
    def __calculate_delay(seconds):
        return datetime.now() + timedelta(seconds=seconds)

    def stop(self):
        self.__handle_stop(None)


def create_skill():
    return AlarmSkill()

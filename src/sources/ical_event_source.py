from icalendar import Calendar
from main.main_logging import get_logger
from utils import find_thing
from utils.nesting_exception import log_exception, log_exception_via
from utils.parsing import local_tz, de_list
from utils.url_load import url_opener
import datetime
import logging
import models
import re
import sys

logger = get_logger(__name__)


def _standard_speaker_parser(component):
    for possible_speaker in de_list(component.get("X-OXTALKS-SPEAKER")):
        return str(possible_speaker)
    return None


def load_ical(opener, raw_hacks=[], master_list=None, lists=[], url_for_logging="unknown", speaker_parser=_standard_speaker_parser):
    """ Utility method to load an ical file and yield the events within it """
    with opener() as stream:
        text = stream.read()
        if text == "":
            logger.debug("ical file from %s was empty" % url_for_logging)
            # Stupid bug in Calendar parser, doesn't accept empty files.
            return

        for raw_hack in raw_hacks:
            text = raw_hack(text)

        calendar = Calendar.from_ical(text)

        for component in calendar.walk('VEVENT'):
            try:
                name = component.get("summary")
                start = component.get("dtstart").dt
                end = component.get("dtend").dt
                location = component.get("location")
                description = component.get("description")
                speaker = speaker_parser(component)

                if not isinstance(start, datetime.datetime) or not isinstance(end, datetime.datetime):
                    continue

                if start.tzinfo is None:
                    start = local_tz.localize(start, is_dst=True)
                if end.tzinfo is None:
                    end = local_tz.localize(end, is_dst=True)
                if len(name) > 0:
                    yield models.Event(name=name, start=start, end=end,
                                       location=location, description=description,
                                       speaker=speaker,
                                       master_list=master_list, lists=lists)
            except Exception:
                log_exception_via(logger.warning, "Failed to create event from url %s" % url_for_logging)


def remove_all_CREATEDs(text):
    """ Very common problem with google ical, events have CREATED dates in the year 0, 
    which confuses the parser (which it shouldn't really) """
    return re.sub("CREATED.*?\n", "", text)


class ICalEventSource(object):
    """ An event source which reads ical data from a specified opener """
    def __init__(self, opener, url_for_logging, master_list_name, name, description, raw_hacks):
        self.opener = opener
        self.url_for_logging = url_for_logging
        self.master_list_name = master_list_name
        self.raw_hacks = raw_hacks
        self.name = name
        self.description = description

    @classmethod
    def create(cls, url=None, name=None, raw_hacks=[], description=None):
        return ICalEventSource(url_opener(url), url, name, name, description,
                               [find_thing(raw_hack_name, sys.modules[__name__]) for raw_hack_name in raw_hacks])

    def __call__(self, list_manager):
        master_list = list_manager.get_or_create_managed_list_by_name(self.master_list_name)
        return load_ical(self.opener, master_list=master_list, lists=[master_list], url_for_logging=self.url_for_logging, raw_hacks=self.raw_hacks)

    def __str__(self):
        return "ICal<%s, %s>" % (self.master_list_name, self.url_for_logging)

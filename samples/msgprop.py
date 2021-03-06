#
# Copyright 2008 The ndb Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Prototype MessageProperty for ProtoRPC.

Run this using 'make x CUSTOM=msgprop'.
"""

import time

from google.appengine.ext import testbed

from protorpc import messages

import ndb
from ndb.msgprop import MessageProperty


# Example classes from protorpc/demos/guestbook/server/

class Note(messages.Message):

  text = messages.StringField(1, required=True)
  when = messages.IntegerField(2)


class GetNotesRequest(messages.Message):

  limit = messages.IntegerField(1, default=10)
  on_or_before = messages.IntegerField(2)

  class Order(messages.Enum):
    WHEN = 1
    TEXT = 2
  order = messages.EnumField(Order, 3, default=Order.WHEN)


class Notes(messages.Message):
  notes = messages.MessageField(Note, 1, repeated=True)


class DbNote(ndb.Model):
  note = MessageProperty(Note)


class DbNotes(ndb.Model):
  danotes = MessageProperty(Notes)


def main():
  tb = testbed.Testbed()
  tb.activate()
  tb.init_datastore_v3_stub()
  tb.init_memcache_stub()

  ctx = ndb.get_context()
  ctx.set_cache_policy(False)
  ctx.set_memcache_policy(False)

  print DbNotes.danotes

  note1 = Note(text='blah', when=int(time.time()))
  print 'Before:', note1
  ent = DbNote(note=note1)
  ent.put()
  print 'After:', ent.key.get()

  print '-' * 20

  note2 = Note(text=u'blooh\u1234\U00102345blooh', when=0)
  notes = Notes(notes=[note1, note2])
  print 'Before:', notes
  ent = DbNotes(danotes=notes)
  print 'Entity:', ent
  print ent._to_pb(set_key=False)
  ent.put()
  pb = ent._to_pb()
  ent2 = DbNotes._from_pb(pb)
  print 'After:', ent.key.get()

  print '-' * 20

  req = GetNotesRequest(on_or_before=42)

  class M(ndb.Model):
    req = MessageProperty(GetNotesRequest)
  m = M(req=req)
  print m
  print m.put().get()

  tb.deactivate()


if __name__ == '__main__':
  main()

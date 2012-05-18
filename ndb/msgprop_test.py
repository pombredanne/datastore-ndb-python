"""Tests for msgprop.py."""

import unittest

from protorpc import messages

from . import model
from . import msgprop
from . import test_utils
from .google_imports import datastore_errors


class Color(messages.Enum):
  RED = 620
  GREEN = 495
  BLUE = 450


SAMPLE_PB = r"""key <
  app: "_"
  path <
    Element {
      type: "Storage"
      id: 1
    }
  >
>
entity_group <
  Element {
    type: "Storage"
    id: 1
  }
>
property <
  name: "greet.text"
  value <
    stringValue: "abc"
  >
  multiple: false
>
raw_property <
  meaning: 14
  name: "greet.__protojson__"
  value <
    stringValue: "{\"text\": \"abc\", \"when\": 123}"
  >
  multiple: false
>
"""


class MsgPropTests(test_utils.NDBTest):

  the_module = msgprop

  def setUp(self):
    super(MsgPropTests, self).setUp()
    global Greeting
    class Greeting(messages.Message):
      text = messages.StringField(1, required=True)
      when = messages.IntegerField(2)
      color = messages.EnumField(Color, 3)

  def testBasics(self):
    class Storage(model.Model):
      greet = msgprop.MessageProperty(Greeting, indexed_fields=['text'])
    greet = Greeting(text='abc', when=123)
    store = Storage(greet=greet)
    key = store.put()
    result = key.get()
    self.assertFalse(result is store)
    self.assertEqual(result.greet.text, 'abc')
    self.assertEqual(result.greet.when, 123)
    self.assertEqual(result.greet, Greeting(when=123, text='abc'))
    self.assertEqual(result,
                     Storage(greet=Greeting(when=123, text='abc'), key=key))
    self.assertEqual(str(result._to_pb()), SAMPLE_PB)

  def testQuery(self):
    class Storage(model.Model):
      greet = msgprop.MessageProperty(Greeting, indexed_fields=['text'])
    greet1 = Greeting(text='abc', when=123)
    store1 = Storage(greet=greet1)
    store1.put()
    greet2 = Greeting(text='def', when=456)
    store2 = Storage(greet=greet2)
    store2.put()
    q = Storage.query(Storage.greet.text == 'abc')
    self.assertEqual(q.fetch(), [store1])
    self.assertRaises(AttributeError, lambda: Storage.greet.when)

  def testErrors(self):
    class Storage(model.Model):
      greet = msgprop.MessageProperty(Greeting, indexed_fields=['text'])

    # Call MessageProperty(x) where x is not a Message class.
    self.assertRaises(TypeError, msgprop.MessageProperty, Storage)
    self.assertRaises(TypeError, msgprop.MessageProperty, 42)
    self.assertRaises(TypeError, msgprop.MessageProperty, None)

    # Call MessageProperty(Greeting, indexed_fields=x) where x
    # includes invalid field names.
    self.assertRaises(ValueError, msgprop.MessageProperty,
                      Greeting, indexed_fields=['text', 'nope'])
    self.assertRaises(TypeError, msgprop.MessageProperty,
                      Greeting, indexed_fields=['text', 42])
    self.assertRaises(TypeError, msgprop.MessageProperty,
                      Greeting, indexed_fields=['text', None])
    self.assertRaises(ValueError, msgprop.MessageProperty,
                      Greeting, indexed_fields=['text', 'text'])  # Duplicate.

    # Set a MessageProperty value to a non-Message instance.
    self.assertRaises(TypeError, Storage, greet=42)

  def testNothingIndexed(self):
    class Store(model.Model):
      gr = msgprop.MessageProperty(Greeting)
    gr = Greeting(text='abc', when=123)
    st = Store(gr=gr)
    st.put()
    self.assertEqual(Store.query().fetch(), [st])
    self.assertRaises(AttributeError, lambda: Store.gr.when)

  def testForceProtocol(self):
    class Store(model.Model):
      gr = msgprop.MessageProperty(Greeting, protocol='protobuf')
    gr = Greeting(text='abc', when=123)
    st = Store(gr=gr)
    st.put()
    self.assertEqual(Store.query().fetch(), [st])

  def testRepeatedMessageProperty(self):
    class StoreSeveral(model.Model):
      greets = msgprop.MessageProperty(Greeting, repeated=True,
                                       indexed_fields=['text', 'when'])
    ga = Greeting(text='abc', when=123)
    gb = Greeting(text='abc', when=456)
    gc = Greeting(text='def', when=123)
    gd = Greeting(text='def', when=456)
    s1 = StoreSeveral(greets=[ga, gb])
    k1 = s1.put()
    s2 = StoreSeveral(greets=[gc, gd])
    k2 = s2.put()
    res1 = k1.get()
    self.assertEqual(res1, s1)
    self.assertFalse(res1 is s1)
    self.assertEqual(res1.greets, [ga, gb])
    res = StoreSeveral.query(StoreSeveral.greets.text == 'abc').fetch()
    self.assertEqual(res, [s1])
    res = StoreSeveral.query(StoreSeveral.greets.when == 123).fetch()
    self.assertEqual(res, [s1, s2])

  def testIndexedEnumField(self):
    class Storage(model.Model):
      greet = msgprop.MessageProperty(Greeting, indexed_fields=['color'])
    gred = Greeting(text='red', color=Color.RED)
    gblue = Greeting(text='blue', color=Color.BLUE)
    s1 = Storage(greet=gred)
    s1.put()
    s2 = Storage(greet=gblue)
    s2.put()
    self.assertEqual(Storage.query(Storage.greet.color == Color.RED).fetch(),
                     [s1])
    self.assertEqual(Storage.query(Storage.greet.color < Color.RED).fetch(),
                     [s2])

  def testRepeatedIndexedField(self):
    class AltGreeting(messages.Message):
      lines = messages.StringField(1, repeated=True)
      when = messages.IntegerField(2)
    class Store(model.Model):
      altg = msgprop.MessageProperty(AltGreeting, indexed_fields=['lines'])
    s1 = Store(altg=AltGreeting(lines=['foo', 'bar'], when=123))
    s1.put()
    s2 = Store(altg=AltGreeting(lines=['baz', 'bletch'], when=456))
    s2.put()
    res = Store.query(Store.altg.lines == 'foo').fetch()
    self.assertEqual(res, [s1])

  def testRepeatedIndexedFieldInRepeatedMessageProperty(self):
    class AltGreeting(messages.Message):
      lines = messages.StringField(1, repeated=True)
      when = messages.IntegerField(2)
    self.assertRaises(TypeError, msgprop.MessageProperty,
                      AltGreeting, indexed_fields=['lines'], repeated=True)

  def testBytesField(self):
    class BytesGreeting(messages.Message):
      data = messages.BytesField(1)
      when = messages.IntegerField(2)
    class Store(model.Model):
      greet = msgprop.MessageProperty(BytesGreeting, indexed_fields=['data'])
    bg = BytesGreeting(data='\xff', when=123)
    st = Store(greet=bg)
    st.put()
    res = Store.query(Store.greet.data == '\xff').fetch()
    self.assertEqual(res, [st])

  def testNestedMessageField(self):
    class Inner(messages.Message):
      count = messages.IntegerField(1)
      greet = messages.MessageField(Greeting, 2)
    class Outer(messages.Message):
      inner = messages.MessageField(Inner, 1)
      extra = messages.StringField(2)
    class Store(model.Model):
      outer = msgprop.MessageProperty(Outer,
                                      indexed_fields=['inner.greet.text'])
    greet = Greeting(text='abc', when=123)
    inner = Inner(count=42, greet=greet)
    outer = Outer(inner=inner)
    st = Store(outer=outer)
    st.put()
    res = Store.query(Store.outer.inner.greet.text == 'abc').fetch()
    self.assertEqual(res, [st])

  def testNestedMessageFieldIsNone(self):
    class Outer(messages.Message):
      greeting = messages.MessageField(Greeting, 1)
    class Store(model.Model):
      outer = msgprop.MessageProperty(Outer, indexed_fields=['greeting.text'])
    outer1 = Outer(greeting=None)
    store1 = Store(outer=outer1)
    store1.put()
    res = Store.query(Store.outer.greeting.text == 'abc').fetch()
    self.assertEqual(res, [])

  def testRepeatedNestedMessageField(self):
    class Outer(messages.Message):
      greeting = messages.MessageField(Greeting, 1)
      extra = messages.IntegerField(2)
    class Store(model.Model):
      outers = msgprop.MessageProperty(Outer, repeated=True,
                                       indexed_fields=['greeting.text'])
    gr1 = Greeting(text='abc', when=123)
    gr2 = Greeting(text='def', when=456)
    outer1 = Outer(greeting=gr1, extra=1)
    outer2 = Outer(greeting=gr2, extra=2)
    store1 = Store(outers=[outer1])
    store1.put()
    store2 = Store(outers=[outer2])
    store2.put()
    store3 = Store(outers=[outer1, outer2])
    store3.put()
    res = Store.query(Store.outers.greeting.text == 'abc').fetch()
    self.assertEqual(res, [store1, store3])

  def testNestedRepeatedMessageField(self):
    class Outer(messages.Message):
      greetings = messages.MessageField(Greeting, 1, repeated=True)
      extra = messages.IntegerField(2)
    class Store(model.Model):
      outer = msgprop.MessageProperty(Outer, indexed_fields=['greetings.text',
                                                             'extra'])
    gr1 = Greeting(text='abc', when=123)
    gr2 = Greeting(text='def', when=456)
    outer1 = Outer(greetings=[gr1], extra=1)
    outer2 = Outer(greetings=[gr2], extra=2)
    outer3 = Outer(greetings=[gr1, gr2], extra=3)
    store1 = Store(outer=outer1)
    store1.put()
    store2 = Store(outer=outer2)
    store2.put()
    store3 = Store(outer=outer3)
    store3.put()
    res = Store.query(Store.outer.greetings.text == 'abc').fetch()
    self.assertEqual(res, [store1, store3])

  def testNestedFieldErrors(self):
    class Outer(messages.Message):
      greetings = messages.MessageField(Greeting, 1, repeated=True)
      extra = messages.IntegerField(2)
    # Parent/child conflicts.
    self.assertRaises(ValueError, msgprop.MessageProperty,
                      Outer, indexed_fields=['greetings.text', 'greetings'])
    self.assertRaises(ValueError, msgprop.MessageProperty,
                      Outer, indexed_fields=['greetings', 'greetings.text'])
    # Duplicate inner field.
    self.assertRaises(ValueError, msgprop.MessageProperty,
                      Outer, indexed_fields=['greetings.text',
                                             'greetings.text'])
    # Can't index MessageField.
    self.assertRaises(ValueError, msgprop.MessageProperty,
                      Outer, indexed_fields=['greetings'])
    # Can't specify subfields for non-MessageField.
    self.assertRaises(ValueError, msgprop.MessageProperty,
                      Outer, indexed_fields=['extra.foobar'])
    # Non-existent subfield.
    self.assertRaises(ValueError, msgprop.MessageProperty,
                      Outer, indexed_fields=['greetings.foobar'])

  def testDoubleNestedRepeatErrors(self):
    class Inner(messages.Message):
      greets = messages.MessageField(Greeting, 1, repeated=True)
    class Outer(messages.Message):
      inner = messages.MessageField(Inner, 1)
      inners = messages.MessageField(Inner, 2, repeated=True)
    msgprop.MessageProperty(Inner, repeated=True)  # Should not fail
    msgprop.MessageProperty(Outer, repeated=True)  # Should not fail
    self.assertRaises(TypeError, msgprop.MessageProperty, Inner,
                      repeated=True, indexed_fields=['greets.text'])
    self.assertRaises(TypeError, msgprop.MessageProperty, Outer,
                      indexed_fields=['inners.greets.text'])
    self.assertRaises(TypeError, msgprop.MessageProperty, Outer,
                       repeated=True, indexed_fields=['inner.greets.text'])

  def testEnumProperty(self):
    class Foo(model.Model):
      color = msgprop.EnumProperty(Color, default=Color.RED,
                                   choices=[Color.RED, Color.GREEN])
      colors = msgprop.EnumProperty(Color, repeated=True)
    foo1 = Foo(colors=[Color.RED, Color.GREEN])
    foo1.put()
    foo2 = Foo(color=Color.GREEN, colors=[Color.RED, Color.BLUE])
    foo2.put()
    res = Foo.query(Foo.color == Color.RED).fetch()
    self.assertEqual(res, [foo1])
    res = Foo.query(Foo.colors == Color.RED).fetch()
    self.assertEqual(res, [foo1, foo2])
    # Test some errors.
    self.assertRaises(datastore_errors.BadValueError,
                      Foo, color=Color.BLUE)  # Not in choices
    self.assertRaises(TypeError, Foo, color='RED')  # Not an enum
    self.assertRaises(TypeError, Foo, color=620)  # Not an enum
    # Invalid default
    self.assertRaises(TypeError, msgprop.EnumProperty, Color, default=42)
    # Invalid choice
    self.assertRaises(TypeError, msgprop.EnumProperty, Color, choices=[42])
    foo2.colors.append(42)
    self.ExpectWarnings()
    self.assertRaises(TypeError, foo2.put)  # Late-stage validation
    class Bar(model.Model):
      color = msgprop.EnumProperty(Color, required=True)
    bar1 = Bar()
    self.assertRaises(datastore_errors.BadValueError, bar1.put)  # Missing value

  def testPropertyNameConflict(self):
    class MyMsg(messages.Message):
      blob_ = messages.StringField(1)
    msgprop.MessageProperty(MyMsg)  # Should be okay
    self.assertRaises(ValueError, msgprop.MessageProperty,
                      MyMsg, indexed_fields=['blob_'])


def main():
  unittest.main()


if __name__ == '__main__':
  main()

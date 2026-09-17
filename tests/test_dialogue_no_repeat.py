import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

from dialogue_generator import dialogue_signature, prepare_dialogue
from dialogue_support import generate, TOPICS
from dialogue_examples import reserve_dialogue
from test_dialogues import example
import test_dialogues as fixtures


def review(letters):
    return dict(valid=True, answers=list(letters), candidates=[[a] for a in letters])


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_correct_key_is_recovered_only_with_independent_confirmation(self):
        data = example()
        data["answers"] = ["F", "D", "B"]  # generator copied the old schema example
        call = AsyncMock(side_effect=[data, review("DAB"), review("EBC"),
                                    {"explanations":example()["explanations"]}, {"valid":True}])
        with patch('dialogue_generator._json_call', call):
            result = await prepare_dialogue('arbejde')
        self.assertEqual(result['answers'], list('DAB'))
        rotated = json.loads(call.call_args_list[2].args[1])
        self.assertEqual(rotated['options']['E'], data['options']['D'])
        self.assertNotIn('answers', rotated)
        self.assertEqual(call.await_count, 5)

    async def test_copied_reviewer_key_cannot_override_generator(self):
        data = example()
        data['answers'] = list('FDB')
        call = AsyncMock(side_effect=[data, review('ABC'), review('ABC')]*3)
        with patch('dialogue_generator._json_call', call):
            with self.assertRaises(ValueError):
                await prepare_dialogue('arbejde')

    async def test_seen_reserve_is_not_saved_or_shown_as_new(self):
        data = reserve_dialogue(TOPICS[3])
        database = AsyncMock(return_value=[dict(data=data)])
        with patch('dialogue_support.db', database), patch('dialogue_support.prepare_dialogue', AsyncMock(side_effect=ValueError())), patch('dialogue_support.send', AsyncMock()) as send, patch('dialogue_support.show', AsyncMock()) as show:
            await generate(object(), 'one', TOPICS[3], 'exam')
        self.assertEqual(database.await_count, 1)
        show.assert_not_awaited()
        self.assertIn('gentager ikke', send.call_args.args[1])

    async def test_duplicate_content_with_new_title_is_rejected_before_review(self):
        previous = example()
        renamed = copy.deepcopy(previous)
        renamed['situation'] = 'A different title'
        call = AsyncMock(return_value=renamed)
        with patch('dialogue_generator._json_call', call):
            with self.assertRaises(ValueError):
                await prepare_dialogue('arbejde', avoid_dialogues=[previous])
        self.assertEqual(call.await_count, 3)


class SignatureTests(unittest.TestCase):
    def test_option_relabelling_and_new_title_do_not_make_new_content(self):
        a = example()
        b = copy.deepcopy(a)
        b['situation'] = 'Another title'
        b['speakers'] = ['Maja', 'Ali']
        b['options'] = dict(zip('FEDCBA', a['options'].values()))
        self.assertEqual(dialogue_signature(a), dialogue_signature(b))
        b['lines'][2] = 'Kan du mødes på lørdag i stedet?'
        self.assertNotEqual(dialogue_signature(a), dialogue_signature(b))


class HistoryTests(unittest.TestCase):
    setUp = fixtures.PersistenceTests.setUp
    tearDown = fixtures.PersistenceTests.tearDown

    def test_seen_history_does_not_forget_after_fifteen_attempts(self):
        from dialogue_support import db_action
        for i in range(17):
            data = example()
            data['situation'] = f'Situation {i}'
            db_action('one', 'create', data=data)
        history = db_action('one', 'recent')
        self.assertEqual(len(history), 17)
        self.assertEqual(history[-1]['data']['situation'], 'Situation 0')
        self.assertEqual(db_action('two', 'recent'), [])

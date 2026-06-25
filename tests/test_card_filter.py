import unittest

from update_cards import (
    get_back_face_data,
    include_for_momir,
)


def base_card(**overrides):
    card = {
        "id": "printing-1",
        "oracle_id": "oracle-1",
        "name": "Test Creature",
        "lang": "en",
        "layout": "normal",
        "border_color": "black",
        "games": ["paper"],
        "cmc": 3,
        "type_line": "Creature — Test",
        "mana_cost": "{2}{G}",
        "oracle_text": "Test rules text.",
        "power": "3",
        "toughness": "3",
    }
    card.update(overrides)
    return card


class CardFilterTests(unittest.TestCase):
    def test_front_creature_is_included_without_artwork(self):
        card = base_card(image_status="missing")
        included, reason = include_for_momir(card, set())
        self.assertTrue(included)
        self.assertEqual(reason, "included")

    def test_battle_with_creature_back_is_excluded(self):
        card = base_card(
            layout="transform",
            type_line="Invasion of Testing // Test Monster",
            card_faces=[
                {
                    "name": "Invasion of Testing",
                    "type_line": "Battle — Siege",
                    "oracle_text": "Battle rules.",
                },
                {
                    "name": "Test Monster",
                    "type_line": "Creature — Beast",
                    "oracle_text": "Creature rules.",
                    "power": "5",
                    "toughness": "5",
                },
            ],
        )
        included, reason = include_for_momir(card, set())
        self.assertFalse(included)
        self.assertEqual(reason, "front_not_creature")

    def test_front_creature_reverse_face_is_stored(self):
        card = base_card(
            layout="transform",
            card_faces=[
                {
                    "name": "Day Creature",
                    "type_line": "Creature — Human",
                    "mana_cost": "{1}{G}",
                    "oracle_text": "Front rules.",
                    "power": "2",
                    "toughness": "2",
                },
                {
                    "name": "Night Creature",
                    "type_line": "Creature — Werewolf",
                    "oracle_text": "Back rules.",
                    "power": "4",
                    "toughness": "4",
                },
            ],
        )
        included, reason = include_for_momir(card, set())
        self.assertTrue(included)
        self.assertEqual(reason, "included")

        back = get_back_face_data(card, {card["id"]: card})
        self.assertIsNotNone(back)
        self.assertEqual(back["name"], "Night Creature")
        self.assertEqual(back["oracle_text"], "Back rules.")


if __name__ == "__main__":
    unittest.main()

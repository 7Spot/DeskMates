"""萨摩耶的自定义毛色——整身一个色 + 可选「背上一片」（coat.TintPainter，包里 coat_custom.mode = "tint"），
设置里「自定义」那一格回来，自定义页两种斑纹（纯色、背上一片）、常用颜色只给自然的毛色，第一次自定义、重置都是雪白（不是边牧的深灰）。"""
import unittest
from unittest import mock

from tests.panel_base import PanelCase
from tests.room_base import HAS, SAMOYED


@unittest.skipUnless(HAS[SAMOYED], "models/samoyed.glb not present (purchased asset)")
class SamoyedCustomCoatTests(PanelCase):
    def setUp(self):
        from widget import packs
        self.enterContext(mock.patch.object(packs, "choose_pet", lambda *a, **k: packs.discover()[SAMOYED]))
        super().setUp()
        self.assertEqual(self.win.pack.id, SAMOYED)

    def test_the_custom_tile_is_back_and_the_page_offers_solid_or_saddle_in_natural_colors(self):
        from widget.coat import TintPainter
        w, s = self.win, self.settings
        self.assertTrue(w.custom_coat_on, "包里打开了 custom_coat")
        self.assertTrue(s.pet_page.isAncestorOf(s.custom_swatch), "设置里「自定义」那一格回来了")
        self.assertIsInstance(w.look.painter(), TintPainter, "通体一色：整身染一个色，不按深浅分")
        page = s.coat_page
        self.assertEqual(sorted(page.pattern_buttons), [1, 2], "两种斑纹：纯色、背上一片")
        self.assertEqual(page.pattern_notes[2].text(), "Saddle · Secondary colour on the back")
        self.assertEqual(len(page.color_chips), 5, "常用颜色按模型给：雪白、奶油、杏、饼干、银灰")
        self.assertEqual(w.common_colors()[0], ("#FFFFFF", "#DDBB8C"))

    def test_the_first_custom_coat_and_reset_start_from_snow_white(self):
        w, s = self.win, self.settings
        self.assertEqual(w.look.coat_spec.main, "#FFFFFF", "没记过自定义：雪白")
        w.open_coat()
        s.finish_page_anim()
        self.assertEqual((w.coat, w.look.coat_spec.main, w.look.coat_spec.pattern), (0, "#FFFFFF", 1), "第一次自定义从雪白开始，不是边牧的深灰")
        page = s.coat_page
        page._set(main="#E6CBA2", pattern=2)
        page.flush()
        self.assertEqual((w.look.coat_spec.main, w.look.coat_spec.pattern), ("#E6CBA2", 2))
        page._reset()
        self.assertEqual((w.look.coat_spec.main, w.look.coat_spec.secondary, w.look.coat_spec.pattern), ("#FFFFFF", "#DDBB8C", 1), "重置：回萨摩耶自己的默认")


if __name__ == "__main__":
    unittest.main()

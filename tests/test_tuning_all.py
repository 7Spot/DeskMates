"""开发者设置里所有的狗、小球、所有物件都能调：物件那一组是包里的 thing.physics（默认值照包里写的），
每个包的调参只有一份（kits.tuning：页上改的、后台备好的、换过去用的、物件落地读的是同一个对象），物件下一次扔、落就用调过的数。"""
import os
import unittest
from dataclasses import fields

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.panel_base import FakeSettings
from widget import packs
from widget.kits import Kits
from widget.things import Thing, ThingPhysics
from widget.tuning import BALL_PARAMS, PET_PARAMS, THING_PARAMS, Tuning, kind_of, params_for


def thing_pack(pack_id: str):
    pack = packs.discover().get(pack_id)
    if pack is None or not pack.things:
        raise unittest.SkipTest(f"没有 {pack_id} 这个物件包")
    return pack


class ThingTuningTests(unittest.TestCase):
    def test_the_table_matches_the_physics_and_its_defaults(self):
        self.assertEqual([p.key for p in THING_PARAMS], [f.name for f in fields(ThingPhysics)], "一项不落，先后一样")
        for p, f in zip(THING_PARAMS, fields(ThingPhysics)):
            self.assertEqual(p.default, f.default, f"{p.key}：没写的物件两边一样")

    def test_each_kind_gets_its_own_table(self):
        found = packs.discover()
        self.assertEqual(kind_of(found[packs.DEFAULT_PET]), "pet")
        self.assertEqual(kind_of(packs.ball_pack()), "ball")
        self.assertEqual(kind_of(thing_pack("bed")), "thing")
        self.assertEqual([p.key for p in params_for(found[packs.DEFAULT_PET])], [p.key for p in PET_PARAMS])
        self.assertEqual([p.key for p in params_for(packs.ball_pack())], [p.key for p in BALL_PARAMS])

    def test_defaults_come_from_the_pack(self):
        for pack_id in ("bed", "doghouse", "food_bowl", "water_bowl"):
            pack = thing_pack(pack_id)
            want = ThingPhysics.of(pack.things[0].spec)
            t = Tuning(pack, FakeSettings())
            for f in fields(ThingPhysics):
                self.assertAlmostEqual(t[f.name], getattr(want, f.name), msg=f"{pack_id} {f.name}")
                self.assertTrue(t.is_default(f.name))

    def test_a_thing_reads_tuned_values_each_time(self):
        pack = thing_pack("doghouse")
        style = pack.things[0]
        t = Tuning(pack, FakeSettings())
        thing = Thing(style, t)
        self.assertEqual(thing.phys, ThingPhysics.of(style.spec), "没调过：包里写的")
        t.set("bounce", 0.5)
        t.set("mass_kg", 3.0)
        self.assertEqual((thing.phys.bounce, thing.phys.mass_kg), (0.5, 3.0), "调了马上用")
        self.assertEqual(thing.phys.friction, ThingPhysics.of(style.spec).friction, "没调的照旧")
        t.reset()
        self.assertEqual(thing.phys, ThingPhysics.of(style.spec))
        self.assertEqual(Thing(style).phys, ThingPhysics.of(style.spec), "没有调参（单测的假 host）：照包里写的")

    def test_copy_values_for_a_thing_goes_into_physics(self):
        t = Tuning(thing_pack("bed"), FakeSettings())
        t.set("squash", 0.2)
        self.assertEqual(t.copy_text(), '"bed": {\n  "physics": {\n    "squash": 0.2\n  }\n}')

    def test_values_are_kept_per_pack(self):
        store = FakeSettings()
        Tuning(thing_pack("bed"), store).set("bounce", 0.3)
        self.assertEqual(Tuning(thing_pack("bed"), store)["bounce"], 0.3, "记在设置里")
        self.assertNotEqual(Tuning(thing_pack("doghouse"), store)["bounce"], 0.3, "各包各记")


class OneTuningPerPackTests(unittest.TestCase):
    def test_kits_hand_out_one_object_per_pack(self):
        kits = Kits(FakeSettings())
        pet = packs.discover()[packs.DEFAULT_PET]
        self.assertIs(kits.tuning(pet), kits.tuning(pet))
        mine = Tuning(packs.ball_pack(), FakeSettings())
        kits.share(mine)
        self.assertIs(kits.tuning(packs.ball_pack()), mine, "别处建好的记成那一份")


if __name__ == "__main__":
    unittest.main()

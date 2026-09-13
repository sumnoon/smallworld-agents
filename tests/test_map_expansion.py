import copy
import json
import tempfile
import unittest
from pathlib import Path
from server.world import World, distance
from server.model import Cognition
from server.maps import obstacle_cells, upgrade_classic
from server.scenario import validate, populate
from test_simulation import quiet, advance

ROOT=Path(__file__).resolve().parents[1]


class ExpandedMapTests(unittest.TestCase):
    def setUp(self):
        self.world=World(cognition=Cognition("demo"),restore=False)
        quiet(self.world)

    def tearDown(self):
        self.world.close()

    def test_expansion_preserves_original_obstacles_and_adds_connected_places(self):
        classic=json.loads((ROOT/"scenarios/classic-neighborhood.json").read_text())
        self.assertEqual(self.world.layout["size"],24)
        old=obstacle_cells(classic)
        self.assertEqual({p for p in self.world.blocked if p[0]<16 and p[1]<16},old)
        for name in ("market","garden","plaza","waterfront"):
            x,y=self.world.layout["places"][name]
            path=self.world.pathfind(self.world.agents["visitor"],{"x":x,"y":y})
            self.assertIsNotNone(path,name)
            self.assertTrue(all(self.world.valid(p["x"],p["y"]) for p in path))

    def test_water_blocks_movement_but_boardwalk_is_walkable(self):
        self.assertFalse(self.world.valid(19,11))
        self.assertTrue(self.world.valid(20,11))
        a={"x":20.,"y":9.}
        path=self.world.pathfind(a,{"x":20,"y":13})
        self.assertTrue(any(p["x"]==20 and p["y"]==11 for p in path))
        self.assertFalse(any(self.world.layout["terrain"][p["y"]][p["x"]]==12 for p in path))

    def test_resident_can_complete_visits_to_new_districts(self):
        for place in ("market","garden","plaza","waterfront"):
            task=self.world.create_task("samir","Visit "+place,{"kind":"visit","place":place})
            advance(self.world,lambda:task["status"]=="completed",1200)
            x,y=self.world.layout["places"][place]
            self.assertLessEqual(distance(self.world.agents["samir"],{"x":x,"y":y}),.8)
            self.assertTrue(task["evidence"])

    def test_player_travel_can_leave_an_interior(self):
        a=self.world.agents["visitor"]
        a.update(room="home",x=2.,y=4.)
        self.world.command({"id":"travel-waterfront","kind":"travel","place":"waterfront"})
        advance(self.world,lambda:not a.get("destination"),1200)
        self.assertEqual(a["room"],"")
        self.assertLessEqual(distance(a,{"x":20,"y":14}),.8)

    def test_requests_accept_the_names_shown_on_the_map(self):
        a=self.world.agents["samir"]
        for request,place in (("Visit Fountain Square","plaza"),("Visit the conservatory","garden"),("Walk to the boardwalk","waterfront")):
            spec=self.world.fallback.task(self.world._context(a,request,request=request))
            self.assertEqual(spec["kind"],"visit")
            self.assertEqual(spec["place"],place)

    def test_landmark_and_terrain_validation(self):
        for change in ("asset","footprint","terrain","disconnected"):
            layout=copy.deepcopy(self.world.layout)
            if change=="asset":layout["landmarks"][0]["asset"]="../../bad"
            if change=="footprint":layout["landmarks"][0]["footprint"]=[0,0,100,100]
            if change=="terrain":layout["terrain"][0]=[0]
            if change=="disconnected":
                for y in range(24):layout["terrain"][y][15]=12
            with self.assertRaises(ValueError,msg=change):validate(layout)
        self.assertEqual(len(populate(self.world.layout,25)["residents"]),26)

    def test_classic_save_upgrades_without_losing_active_task_or_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            database=Path(tmp)/"town.db"
            old=World(database,cognition=Cognition("demo"),restore=False,scenario=ROOT/"scenarios/classic-neighborhood.json")
            quiet(old)
            old.agents["samir"]["inventory"]=[{"id":"saved-coffee","kind":"coffee"}]
            old.stock["coffee"]=11
            task=old.create_task("samir","Wait",{"kind":"wait","minutes":3})
            tid=task["id"];position=(old.agents["samir"]["x"],old.agents["samir"]["y"])
            old.close()
            restored=World(database,cognition=Cognition("demo"))
            try:
                self.assertEqual(restored.layout["size"],24)
                self.assertEqual(restored.agents["samir"]["task"],tid)
                self.assertEqual(restored.agents["samir"]["inventory"][0]["id"],"saved-coffee")
                self.assertEqual(restored.stock["coffee"],11)
                self.assertEqual((restored.agents["samir"]["x"],restored.agents["samir"]["y"]),position)
                self.assertEqual(restored.storage.load()["layout"]["size"],24)
            finally:restored.close()

    def test_custom_map_is_not_replaced_by_save_upgrade(self):
        classic=json.loads((ROOT/"scenarios/classic-neighborhood.json").read_text())
        classic["props"].append({"i":0,"x":15,"y":15,"w":90})
        result,changed=upgrade_classic(classic)
        self.assertFalse(changed)
        self.assertEqual(result,classic)

    def test_new_sprite_manifest_entries_are_real_transparent_assets(self):
        manifest=json.loads((ROOT/"assets/manifest.json").read_text())
        for name in ("market-pavilion","garden-conservatory","plaza-fountain","blossom-tree"):
            sheet=manifest["sheets"][name]
            self.assertGreater(sheet["transparentPercent"],10)
            self.assertEqual(len(sheet["frames"]),1)
            self.assertTrue((ROOT/"assets"/sheet["file"]).is_file())

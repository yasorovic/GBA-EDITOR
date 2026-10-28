function on_collision_enter(other, my_box, other_box)
	if other_box.tag == "player" then
		scene:switch("Scene_01")
	end
end

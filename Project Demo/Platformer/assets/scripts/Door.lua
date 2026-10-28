function on_collision_enter(other, my_box, other_box)
	if other_box.tag == "player" then
		sfx:play("sfx_exit")
		scene:switch("Scene_01")
	end
end

function on_actor_enter(other, other_box)
	if other_box.tag == "player" then
		sfx:play("sfx_exit")
		scene:switch("Scene_01")
	end
end

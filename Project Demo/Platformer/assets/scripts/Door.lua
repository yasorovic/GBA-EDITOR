function on_start()
end

function on_update()
end

function on_collision_enter(other, my_box, other_box)
	if other_box.tag == "player" then
		scene:switch("Scene_2")
	end
end

function on_collision_exit(other, my_box, other_box)
end

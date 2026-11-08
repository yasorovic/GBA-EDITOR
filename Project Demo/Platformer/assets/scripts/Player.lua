exports = {
    move_speed = { type = "int", default = 2, label = "Speed", min = 0, max = 8 },
    jump_force ={ type = "int", default = 900, label = "Jump Force", min = 0, max = 2048 },
}

local air_frames = 0 -- frames since the last contact with the ground

function on_start()
	self:play_anim("idle")
	self.facing_auto = true -- the sprite looks where the player last moved

end

function on_update()
	local body = self:physics_body()

	if body.grounded then
		if air_frames > 4 then sfx:play("sfx_land") end -- a real fall, not a flicker on a slope
		air_frames = 0
	else
		air_frames = air_frames + 1
	end

	local move_dir = input:get_axis("horizontal")

	local x_speed = move_dir * move_speed * 256
	local y_speed = body.velocity.y -- the engine adds the scene gravity (Use scene gravity)

	if body.grounded and input:pressed("a") then --Jump
        y_speed = -jump_force
        sfx:play("sfx_jump")
    end


    if body.grounded and move_dir ~= 0 then self:play_anim("moving")

    elseif body.grounded then self:play_anim("idle")

    else self:play_anim("jumping") end

    body.velocity = vec2(x_speed, y_speed)
    body:apply_velocity()

end

exports = {
    move_speed = { type = "int", default = 2, label = "Vitesse", min = 0, max = 8 },
    gravity = { type = "int", default = 9, label = "Gravité", min = 0, max = 256 },
    jump_force ={ type = "int", default = 900, label = "Force de saut", min = 0, max = 2048 },
}

function on_start()
	self:play_anim("idle")
	self.auto_dir = false
    
end

function on_update()
	
	local move_dir = input:get_axis("horizontal")
	
	local x_speed = move_dir * move_speed * 256
	local y_speed = self.velocity.y
	
	if not self.grounded then y_speed = self.velocity.y + gravity end --apply gravity
	
	if self.grounded and input:pressed("a") then --Jump
        y_speed = -jump_force
    end


    if self.grounded and x_speed  then self:play_anim("moving")
    
    elseif self.grounded and not x_speed then self:play_anim("idle")
    
    elseif not self.grounded then self:play_anim("jumping") end
    
    self.velocity = vec2(x_speed, y_speed)
    self:apply_velocity()
    
    if x_speed then self.direction = vec2(move_dir, 0) end
    
end

function on_collision_enter(other, my_box, other_box)
end

function on_collision_exit(other, my_box, other_box)
end

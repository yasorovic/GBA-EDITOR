local walking = 0

function on_start()
    self:play_anim("Idle")
end

function on_update()
    local dx = input:get_axis("horizontal")
    local dy = input:get_axis("vertical")
    if global.talking == 1 then
        dx = 0
        dy = 0
    end
    if dx ~= 0 then
        dy = 0
    end
    self.velocity = vec2(dx * 384, dy * 384)
    self:apply_velocity()

    local moving = 0
    if dx ~= 0 or dy ~= 0 then
        moving = 1
    end
    if moving ~= walking then
        walking = moving
        if moving == 1 then
            self:play_anim("Walk")
        else
            self:play_anim("Idle")
        end
    end
end

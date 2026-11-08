exports = {
    speed = { type = "int", default = 1, label = "Vitesse", min = 0, max = 4 },
    dir = { type = "int", default = 1, label = "Sens", min = -1, max = 1 },
}

local started = false -- no move yet on the first frame: a zero speed means nothing

function on_start()
    self:play_anim("moving")
end

function on_update()
    local body = self:physics_body()

    -- the engine cancels the horizontal speed when a wall of the map or a Block shape stops the guard
    if started and body.velocity.x == 0 then
        dir = -dir -- turn back
    end
    started = true

    body.velocity = vec2(dir * speed * 256, body.velocity.y) -- keep the fall given by the scene gravity
    body:apply_velocity()
end

function on_start()
    self:play_anim("Idle")
    local corps = self:collision_box("body")
    local frappe = self:collision_box("hitbox")

    frappe.offset = vec2(8, -4)
    frappe.size = vec2(20, 8)
    frappe:deactivate()
end

function on_update()
    local corps = self:collision_box("body")
    local frappe = self:collision_box("hitbox")
    if input:pressed("b") then
        frappe:activate()
    end
    local ennemi = actor:get("Hero")
    if ennemi and frappe:overlaps(ennemi) then
        corps.solid = true
    end
    local sol = corps:get_collision_tile(corps.bounds.x, corps.bounds.y + corps.bounds.h)
    if sol == 0 and corps.is_grounded then
        corps.solid = true
    end
end

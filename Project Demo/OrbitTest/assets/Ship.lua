exports = {
    move_speed = { type = "int", default = 1, label = "Vitesse", min = 0, max = 8 },
    left_limit = { type = "int", default = 48, label = "Limite gauche" },
    right_limit = { type = "int", default = 176, label = "Limite droite" },
    orbit_speed = { type = "int", default = 3, label = "Vitesse de l'orbite (deg par frame)", min = 0, max = 20 },
}

local direction = 1

-- Moon est enfant de Ship : le build la replace chaque frame a un decalage fixe,
-- tourne par la rotation de Ship. Faire tourner Ship (sans afficher cette rotation :
-- son sprite n'est pas affine) fait donc orbiter Moon autour de lui.
function on_update()
    local x = self.position.x + direction * move_speed
    if x >= right_limit then direction = -1 end
    if x <= left_limit then direction = 1 end
    self.position = vec2(x, 64)
    self.rotation = (self.rotation + orbit_speed) % 360
end

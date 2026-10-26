-- Le héros né avance vers la droite à 2 px par image : le mur né doit l'arrêter.
function on_update()
    self.velocity = vec2(512, 0)
    self:apply_velocity()
end

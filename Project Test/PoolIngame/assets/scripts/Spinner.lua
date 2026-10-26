-- Un modèle affine né : il tourne de 4 degrés par image (chaque sprite dessiné prend une des 32 matrices).
function on_update()
    self.rotation = self.rotation + 4
end

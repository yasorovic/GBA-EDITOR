function on_start()
    self.Voyant:hide()
end

function on_update()
    if input:pressed("a") then
        self.Canon:play_anim("tir")
        self.Voyant:show()
    end

    local joueur = actor:get("Joueur")
    if joueur then
        self.Voyant:show()
    else
        self.Voyant:hide()
        self.Canon:hide()
    end
end

# Diagramme d'architecture

Vue d'ensemble des couches, dérivée du code réel (pas des noms de fichiers). Le détail
vit dans [ARCHITECTURE.md](ARCHITECTURE.md) ;
Rendu par GitHub / Mermaid. À régénérer à la main quand une couche bouge. Ce fichier n'est pas
auto-généré, pour rester fidèle aux relations et pas aux fichiers.

```mermaid
graph TD
    dev([Game Developer])

    subgraph shell["Application Shell — editor/"]
        main["main.py — point d'entrée"]
        window["window.py — MainWindow + onglets"]
        project["Project (project.py)<br/>+ tranches : paths / variables /<br/>texts / langs / renames"]
    end

    subgraph domain["Modèle de domaine — core/models/ (SOURCE DE VÉRITÉ)"]
        models["scene · sprite · background · palette<br/>font · text · camera · ui_region<br/>data_table · components · ids · tile_codec"]
    end

    subgraph bus["Bus transverses — core/"]
        dispatcher["command_dispatcher"]
        history["history (undo/redo)"]
        selection["selection_bus"]
        events["events"]
        watcher["project_watcher"]
    end

    subgraph persist["Persistance — core/resources/"]
        store["resource_index · resource_store<br/>palette_store · asset_reconciliation"]
    end

    disk[("Disque projet<br/>assets/ + project/<br/>+ &lt;Nom&gt;.project")]

    subgraph ui["Écrans — editor/ui/ (rangés par écran)"]
        screens["home · scene_manager · sprite_editor<br/>palette_editor · background_editor<br/>data_editor · sound_mixer<br/>script_editor · text_editor"]
        common["common/ — theme (C/T) · labels · notices · catalog"]
    end

    subgraph twins["Aperçus jumeaux — core/engine_emulation/<br/>(ce que l'éditeur REFAIT en Python)"]
        emu["text_layout · blend_preview<br/>module_render · music_deck"]
    end

    subgraph script["Compilation Lua → C — scripting/"]
        parser["parser.py → AST"]
        checker["checker.py — validation"]
        scodegen["codegen.py → texte C"]
        api["api.py (RUNTIME_API)<br/>+ lua_subset · expr_types"]
    end

    subgraph gen["Génération ROM — codegen/"]
        rombuild["rom_build.py — BuildWorker (orchestration)"]
        runtimecg["runtime_codegen/ — main.c · scènes · acteurs · data_tables"]
        alloc["Allocateurs matériels<br/>vram_alloc · palette_alloc<br/>oam_alloc · window_alloc"]
        emit["Émission assets<br/>bg_emit · font_emit · font_build<br/>grit_conversion · sfx_encode"]
    end

    subgraph rt["Runtime GBA — runtime/ (C écrit à la main, DONNÉE pour l'éditeur)"]
        engine["gba_engine.h · actor_api_static.h · runtime.h"]
    end

    subgraph ext["Outils externes"]
        toolchain["toolchain.py — détection devkitPro / mGBA"]
        devkit["devkitPro (arm-none-eabi-gcc) · grit"]
        rom["ROM .gba"]
        mgba["mGBA"]
    end

    dev --> main
    main --> window
    main --> project
    window --> screens

    project --> models
    project <--> store
    store <--> disk
    watcher -. surveille .-> disk

    screens <--> dispatcher
    dispatcher --> history
    dispatcher --> models
    screens --> selection
    screens --> events
    screens --> common
    screens -. aperçu WYSIWYG .-> emu
    emu -. jumeau des formules de .-> engine

    disk -->|assets/scripts Lua| parser
    parser --> checker --> scodegen
    api --- checker
    api --- scodegen

    project --> rombuild
    scodegen --> runtimecg
    rombuild --> runtimecg
    rombuild --> alloc
    rombuild --> emit
    emit --> devkit
    runtimecg --> engine
    rombuild --> engine

    rombuild --> toolchain
    toolchain --> devkit
    devkit --> rom
    rom -. chargée dans .-> mgba
    toolchain -. lance .-> mgba

    classDef vt fill:#0b7285,color:#fff,stroke:#0b7285;
    class domain,models vt
```

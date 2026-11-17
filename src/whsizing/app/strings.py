"""FR / EN texts of the app chrome (page titles, buttons, help lines).

The report package owns everything it already says in two languages: the "indicative study"
banner, table labels, units, number and date formats (`whsizing.report.i18n`). Only what the
report has no text for lives here: `UI[key] = (french, english)`; `tr` fills `{placeholders}`.
"""

from __future__ import annotations

from whsizing.report import Lang

UI: dict[str, tuple[str, str]] = {
    # -- shared
    "run": ("Run", "Run"),
    "no_run": (
        "Aucun run pour le moment. Ouvrez la page 1 (Téléversement) pour charger des données, "
        "ou choisissez un run existant sur la page d'accueil.",
        "No run yet. Open page 1 (Upload) to load data, or pick an existing run on the home page.",
    ),
    "stage_missing": (
        "Ce run est à l'étape « {have} » ; cette page demande l'étape « {stage} ». Suivez les "
        "pages dans l'ordre (1 à 6).",
        "This run is at stage '{have}'; this page needs stage '{stage}'. Follow the pages in "
        "order (1 to 6).",
    ),
    # -- home
    "home.title": ("Dimensionnement d'entrepôt", "Warehouse sizing"),
    "home.intro": (
        "Étude indicative : données client, profil de demande, base de conception, scénarios, "
        "résultats traçables.",
        "Indicative study: client data, demand profile, design basis, scenarios, traceable "
        "results.",
    ),
    "home.local": (
        "Tout reste sur cette machine : aucun appel réseau, aucune télémétrie.",
        "Everything stays on this machine: no network call, no telemetry.",
    ),
    "home.runs": ("Runs", "Runs"),
    "home.no_runs": ("Aucun run dans {root}.", "No run in {root}."),
    "home.open": ("Ouvrir un run", "Open a run"),
    "home.new": ("Nouveau run", "New run"),
    "home.pages": ("Pages", "Pages"),
    "home.steps": (
        "1 Téléversement et mapping\n2 Qualité des données\n3 Profil de demande\n"
        "4 Base de conception\n5 Scénarios\n6 Résultats",
        "1 Upload and mapping\n2 Data quality\n3 Demand profile\n4 Design basis\n5 Scenarios\n"
        "6 Results",
    ),
    # -- page 1
    "upload.title": ("1 Téléversement et mapping", "1 Upload and mapping"),
    "upload.privacy": (
        "Les fichiers sont écrits dans le dossier des runs de cette machine.",
        "Files are written to the runs folder of this machine.",
    ),
    "upload.dataset": ("Jeu de données", "Dataset"),
    "upload.order": (
        "Chargez d'abord sku_master : les autres jeux sont contrôlés contre lui.",
        "Load sku_master first: the other datasets are checked against it.",
    ),
    "upload.files": ("Fichiers (CSV, Excel, Parquet)", "Files (CSV, Excel, Parquet)"),
    # the one field that reads an arbitrary path: the machine running the app, local use only
    "upload.path": (
        "ou chemin sur la machine qui exécute l'application (usage local uniquement ; "
        "fichier volumineux, motif accepté)",
        "or a path on the machine running the app (local use only; large file, glob accepted)",
    ),
    "upload.nothing": ("Aucun fichier choisi.", "No file chosen."),
    "upload.too_big": (
        "{name} est trop gros pour être téléversé ici : utilisez la ligne de commande.",
        "{name} is too large to upload here: use the command line.",
    ),
    "upload.sniff": ("Lecture du fichier", "What was read"),
    "upload.mapping": ("Mapping des colonnes", "Column mapping"),
    "upload.ingest": ("Ingestion", "Ingest"),
    "upload.salt": (
        "Sel d'anonymisation (jamais écrit sur disque)",
        "Anonymisation salt (never written to disk)",
    ),
    "upload.salt_needed": (
        "Saisissez le sel, ou exportez WHSIZING_SALT avant de lancer l'application.",
        "Enter the salt, or export WHSIZING_SALT before starting the app.",
    ),
    "upload.add_to_run": ("Ajouter au run {run}", "Add to run {run}"),
    "upload.run": ("Lancer l'ingestion", "Run ingest"),
    "upload.running": ("Ingestion en cours...", "Ingesting..."),
    "upload.done": (
        "Run {run} : score qualité {score} ({band}). Suite : page 2.",
        "Run {run}: quality score {score} ({band}). Next: page 2.",
    ),
    "upload.see_dq": (
        "Le dossier du run est conservé : la page 2 explique le problème.",
        "The run folder is kept: page 2 explains the problem.",
    ),
    "map_target": ("Cible", "Target"),
    "map_column": ("Colonne", "Column"),
    "map_score": ("Score", "Score"),
    "map_status": ("Statut", "Status"),
    "map_accept": ("Accepter", "Accept"),
    "unit_hint": (
        "{code} : {why} ; les valeurs semblent en {unit}. Convertir en {base} ({op}) ?",
        "{code}: {why}; values look like {unit}. Convert to {base} ({op})?",
    ),
    # -- page 2
    "dq.title": ("2 Qualité des données", "2 Data quality"),
    "dq.none": ("Pas encore de rapport de qualité.", "No data-quality report yet."),
    "dq.score": ("Score qualité", "Quality score"),
    "dq.blocking": ("Problèmes bloquants ({n})", "Blocking issues ({n})"),
    "dq.no_blocking": ("Aucun problème bloquant.", "No blocking issue."),
    "dq.warnings": ("Avertissements ({n})", "Warnings ({n})"),
    "dq.sample": ("Exemples de lignes concernées", "Sample of the rows concerned"),
    "dq.coverage": ("Couverture", "Coverage"),
    "dq.download": ("Télécharger le rapport HTML", "Download the HTML report"),
    # -- page 3
    "profile.title": ("3 Profil de demande", "3 Demand profile"),
    "profile.running": ("Calcul du profil...", "Building the profile..."),
    "profile.period": ("Période", "Period"),
    "profile.days": ("Jours ouvrés", "Operating days"),
    "profile.peak": ("Pointe / moyenne", "Peak to average"),
    "profile.dims": ("Lignes avec dimensions", "Lines with dimensions"),
    "profile.eiq": ("Structure des commandes (EIQ)", "Order structure (EIQ)"),
    "profile.metric": ("Mesure", "Measure"),
    "profile.lines_per_order": ("Lignes par commande", "Lines per order"),
    "profile.units_per_line": ("Unités par ligne", "Units per line"),
    "profile.units_per_order": ("Unités par commande", "Units per order"),
    "profile.cube_per_order": ("Volume par commande (m3)", "Cube per order (m3)"),
    "profile.weight_per_order": ("Poids par commande (kg)", "Weight per order (kg)"),
    "profile.classes": ("Classes de commandes", "Order classes"),
    "profile.single_line": ("mono-ligne", "single-line"),
    "profile.split": ("Répartition colis / palettes", "Parcel / pallet split"),
    "profile.kind": ("Type", "Kind"),
    "profile.parcel": ("Colis", "Parcel"),
    "profile.pallet": ("Palette", "Pallet"),
    "profile.share_orders": ("Part des commandes", "Share of orders"),
    "profile.share_lines": ("Part des lignes", "Share of lines"),
    "profile.parcels_per_order": (
        "Colis par commande colis : {n}",
        "Parcels per parcel order: {n}",
    ),
    # -- page 4
    "basis.title": ("4 Base de conception", "4 Design basis"),
    "basis.intro": (
        "[CLIENT] : valeur client obligatoire (exemple affiché) ; [P] : valeur par défaut "
        "provisoire à confirmer. L'aperçu se met à jour à chaque modification.",
        "[CLIENT]: required client value (example shown); [P]: placeholder default to confirm. "
        "The preview updates with every change.",
    ),
    "basis.sealed": (
        "Ce run est dimensionné et les runs sont immuables : voici la base utilisée.",
        "This run is sized and runs are immutable: this is the basis it used.",
    ),
    "basis.preview": ("Jour de conception (aperçu)", "Design day (preview)"),
    "basis.reference": (
        "Percentile {percentile:g} ; jour de référence {date}",
        "Percentile {percentile:g}; reference day {date}",
    ),
    "basis.save": ("Enregistrer la base", "Save the basis"),
    "basis.saved": ("Base enregistrée : {path}", "Basis saved: {path}"),
    "tag_client": ("[CLIENT]", "[CLIENT]"),
    "tag_default": ("[P]", "[P]"),
    "tag_modified": ("(modifié)", "(modified)"),
    "default_is": ("Défaut : {value}", "Default: {value}"),
    "dd.metric": ("Mesure", "Measure"),
    "dd.value": ("Valeur", "Value"),
    "dd.lines": ("Lignes / jour", "Lines / day"),
    "dd.orders": ("Commandes / jour", "Orders / day"),
    "dd.units": ("Unités / jour", "Units / day"),
    "dd.cube_m3": ("Volume (m3) / jour", "Cube (m3) / day"),
    "dd.peak_hour_lines": ("Lignes à l'heure de pointe", "Lines in the peak hour"),
    "dd.parcels": ("Colis / jour", "Parcels / day"),
    "dd.pallets_out": ("Palettes sortantes / jour", "Outbound pallets / day"),
    "dd.stock_cube_m3": ("Volume de stock (m3)", "Stock cube (m3)"),
    # -- page 5
    "scn.title": ("5 Scénarios", "5 Scenarios"),
    "scn.sealed": (
        "Ce run est dimensionné et les runs sont immuables : voici les scénarios utilisés.",
        "This run is sized and runs are immutable: these are the scenarios it used.",
    ),
    "scn.add": ("Ajouter un scénario", "Add a scenario"),
    "scn.none": (
        "Aucun scénario : ajoutez-en un pour dimensionner.",
        "No scenario: add one to size.",
    ),
    "scn.save": ("Enregistrer scenarios.yaml", "Save scenarios.yaml"),
    "scn.saved": ("Scénarios enregistrés : {path}", "Scenarios saved: {path}"),
    "scn.size": ("Dimensionner et comparer", "Size and compare"),
    "scn.sizing": ("Dimensionnement et comparaison...", "Sizing and comparing..."),
    "scn.sized": (
        "Run dimensionné. Suite : page 6.",
        "Run sized. Next: page 6.",
    ),
    "scn.need_basis": (
        "La base de conception est absente ou invalide : corrigez-la page 4.",
        "The design basis is missing or invalid: fix it on page 4.",
    ),
    "baseline": ("Référence de comparaison", "Comparison baseline"),
    "sc_id": ("Id", "Id"),
    "sc_name": ("Nom", "Name"),
    "sc_family": ("Famille", "Family"),
    "sc_overrides": ("Paramètres du catalogue à modifier", "Catalog parameters to override"),
    "sc_out_of_range": (
        "{pid} = {value:g} est hors de [{lo:g}, {hi:g}] : le curseur montre la borne la "
        "plus proche.",
        "{pid} = {value:g} is outside [{lo:g}, {hi:g}]: the slider shows the nearest bound.",
    ),
    "sc_use_limits": ("Limites du catalogue", "Catalog limits"),
    "sc_assume_dims": ("Éligible sans dimensions", "Eligible without dimensions"),
    "sc_extra_weight": ("Poids max. supplémentaire (kg)", "Extra max weight (kg)"),
    "sc_remove": ("Supprimer ce scénario", "Remove this scenario"),
    # -- page 6
    "results.title": ("6 Résultats", "6 Results"),
    "results.all_worlds": ("Afficher bas / haut", "Show lo / hi"),
    "results.comparison": ("Comparaison", "Comparison"),
    "results.fte": ("Effectifs (ETP)", "Staffing (FTE)"),
    "results.area": ("Surfaces (schéma en blocs)", "Areas (block diagram)"),
    "results.business": ("Business case", "Business case"),
    "results.sensitivity": ("Sensibilité", "Sensitivity"),
    "results.no_sensitivity": (
        "Pas d'analyse de sensibilité pour ce run.",
        "No sensitivity analysis for this run.",
    ),
    "results.no_chart": ("Pas de données pour ce graphique.", "No data for this chart."),
    "results.not_computed": (
        "{sid} non calculé : {reason}",
        "{sid} not computed: {reason}",
    ),
    "results.why": ("Pourquoi ce chiffre ?", "Why this number?"),
    "results.why_help": (
        "Cliquez une cellule du tableau de synthèse (ou choisissez-la ci-dessous) : son calcul "
        "est déplié jusqu'aux paramètres et aux données.",
        "Click a cell of the summary table (or pick it below): its calculation is unfolded down "
        "to the parameters and the data.",
    ),
    "results.export": ("Exports", "Exports"),
    "results.dl_comparison": ("Télécharger comparison.json", "Download comparison.json"),
    "results.build": ("Générer le {kind}", "Build the {kind}"),
    "results.building": ("Génération...", "Building..."),
    "results.unavailable": (
        "Export {kind} indisponible dans cette version.",
        "{kind} export is not available in this build.",
    ),
    # -- drill-down
    "drill.cell": ("Cellule du tableau de synthèse", "Summary cell"),
    "drill.trace_id": (
        "ou identifiant de trace (ex. S1.area.total)",
        "or a trace id (e.g. S1.area.total)",
    ),
    "drill.picked": (
        "Cellule choisie : {cell}. Son calcul est déplié plus bas, sous « Pourquoi ce chiffre ? ».",
        "Cell picked: {cell}. Its calculation is unfolded below, under 'Why this number?'.",
    ),
    "drill.none": ("Aucune cellule tracée.", "No traced cell."),
    "drill.unknown": ("Identifiant de trace inconnu : {id}", "Unknown trace id: {id}"),
    "drill.depth": ("Profondeur affichée", "Depth shown"),
    "drill.size": (
        "{shown} nœuds affichés sur {total} (l'arbre complet répète les sous-résultats partagés)",
        "{shown} nodes shown of {total} (the full tree repeats shared sub-results)",
    ),
    "drill.reroot": (
        "Repartir d'un nœud coupé (augmente le détail)",
        "Re-root on a cut node (more detail)",
    ),
    "leaf_param": ("paramètre", "parameter"),
    "leaf_dataset": ("donnée", "data"),
    "leaf_unresolved": ("non résolu", "unresolved"),
    "leaf_cycle": ("cycle", "cycle"),
    "hidden_inputs": ("{n} entrée(s) masquée(s)", "{n} input(s) hidden"),
}

SECTIONS: dict[str, tuple[str, str]] = {
    "general": ("Général", "General"),
    "operations": ("Exploitation", "Operations"),
    "service": ("Service", "Service"),
    "projection": ("Projection", "Projection"),
    "flows": ("Flux", "Flows"),
    "building": ("Bâtiment", "Building"),
    "finance": ("Finance", "Finance"),
    "baseline": ("Situation actuelle", "Current operation"),
    "overrides": ("Surcharges de paramètres", "Parameter overrides"),
}


def tr(key: str, lang: Lang, **fmt: object) -> str:
    """The text of `key` in `lang`; `{name}` placeholders are filled from `fmt`."""
    french, english = UI[key]
    text = french if lang == "fr" else english
    return text.format(**fmt) if fmt else text


def section_title(group: str, lang: Lang) -> str:
    french, english = SECTIONS.get(group, (group, group))
    return french if lang == "fr" else english

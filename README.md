# Trieur de photos

Programme Windows en français pour **ranger, renommer et dédoublonner** des photos et des vidéos.

## Installation

Téléchargez l'installateur :
**https://github.com/naviletrou/Trieur-photos/releases/download/derniere-version/TrieurPhotos-Installation.exe**

Le programme n'est pas signé : Windows peut afficher « Windows a protégé votre ordinateur ».
Cliquez sur **Informations complémentaires**, puis **Exécuter quand même**.
L'installation ne demande pas de droits d'administrateur.

Une version sans installation est aussi disponible (`TrieurPhotos-portable.zip`, même adresse).

## Ce qu'il fait

1. **Dossiers** : choix des photos à ranger et de la destination, en copie (conseillé) ou en déplacement.
2. **Classement** : modèle de dossiers et de noms à partir d'étiquettes (année, mois, jour, lieu,
   événement, appareil…), avec un exemple construit à partir de vos photos. Modèle proposé :
   `2001 / 07 - Juillet / 2001-07-11 Cheverny - Visite du château / 2001-07-11_14h32_Cheverny.jpg`
3. **Vérification** : photos regroupées par jour. On corrige la date, le lieu ou l'événement d'un
   groupe (ou de plusieurs à la fois). Les groupes douteux sont signalés.
4. **Doublons** : fichiers identiques, même photo en plusieurs versions (réduite, envoyée par
   messagerie…), photos presque identiques prises en rafale. Rien n'est jamais supprimé.
5. **Lancement** : classement, journal de toutes les opérations et **annulation complète** possible.

### Mode « Rechercher les doublons dans ma photothèque »

Pour une photothèque déjà rangée (sur le PC ou sur le réseau) : rien n'est reclassé ni renommé.
Les doublons trouvés sont présentés côte à côte ; ceux que l'on écarte sont déplacés dans
`_Doublons` à la racine de la photothèque, avec leur chemin d'origine. La copie gardée est la mieux
rangée (dossier daté ou nommé plutôt que « Divers » ou « À trier », nom d'origine plutôt que
« Copie de… »), ou celle d'un dossier préféré que l'on choisit. Une liste des doublons peut être
exportée pour Excel. Tout peut être remis en place grâce au journal.

Avec Immich : ajoutez `**/_Doublons/**` aux motifs d'exclusion de la bibliothèque externe.

### D'où viennent la date et le lieu

* **Date** : date de prise de vue (EXIF, vidéo), sinon date dans le nom du fichier
  (`IMG_20190812_143201`), sinon dans le nom du dossier (`2001-07-11 Cheverny`, `1985 Noël`),
  sinon, en option, date du fichier. Les dates enregistrées par un scanner sont ignorées.
  La date trouvée peut être écrite dans les photos qui n'en ont pas (scans).
* **Lieu** : commune la plus proche des coordonnées GPS, sans connexion internet
  (base GeoNames : toutes les communes françaises et les villes du monde).
* **Événement** : proposé d'après le nom des dossiers datés, modifiable.

### Fichiers associés

Les fichiers `.xmp`, `.aae`, les fichiers RAW pris avec un JPEG et la vidéo d'une Live Photo
suivent leur photo et prennent le même nom.

### Avec Immich

Immich reconnaît une photo à son chemin : une photo renommée ou déplacée dans une bibliothèque
déjà indexée y est vue comme une nouvelle photo. Le plus simple : classer l'archive une fois,
puis utiliser un dossier « À trier » pour les nouvelles photos, classées ensuite dans la photothèque.

## Pour les développeurs

```
pip install PySide6 Pillow pillow-heif numpy babel pytest
python tools/build_places.py geonames DOSSIER_GEONAMES   # base des lieux
python -m trieur                                         # lancement
python -m pytest                                         # tests (ExifTool nécessaire)
```

L'installateur est fabriqué par GitHub Actions (`.github/workflows/windows.yml`) à chaque
modification de la branche `main`.

Crédits : [ExifTool](https://exiftool.org) de Phil Harvey ;
lieux © [GeoNames](https://www.geonames.org), licence CC BY 4.0 ; interface Qt for Python (LGPL).

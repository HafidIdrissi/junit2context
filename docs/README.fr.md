# junit2context

**Transformez vos rapports JUnit XML en un résumé utile pour déboguer.**

[English README](../README.md) · [Contribuer](../CONTRIBUTING.md) · [Feuille de route](ROADMAP.md)

`junit2context` extrait les tests en échec, déduplique les échecs identiques, masque certains motifs de secrets courants et produit un document Markdown à lire ou à transmettre à votre assistant de programmation.

Tout fonctionne localement avec la bibliothèque standard de Python. Aucun modèle, aucune clé API, aucun appel réseau et aucune exécution de tests.

## Démonstration

Depuis les fichiers téléchargés, ouvrez [demo.html](demo.html) dans votre navigateur : une démo interactive de 30 secondes montre la sortie réelle du programme, entièrement hors ligne. Sur GitHub, téléchargez le fichier HTML pour le lire localement.

Les deux exemples fournis passent de 1 622 caractères XML à un résumé de 864 caractères, soit 46,7 % de moins sur ces exemples. Il ne s'agit ni d'un benchmark ni d'une estimation de tokens. Consultez le [résumé généré](../examples/brief.md). La commande `python3 scripts/build_demo.py` régénère la démo et le résumé.

## Installation et essai

Python 3.10 ou plus récent est nécessaire.

```bash
git clone https://github.com/HafidIdrissi/junit2context.git
cd junit2context
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/junit2context examples/pytest.xml examples/vitest.xml \
  --max-chars 6000 --output failures.md
```

Sous Windows, utilisez `python` et les exécutables du dossier `.venv\Scripts\`.

Sans installation, depuis le dépôt :

```bash
PYTHONPATH=src python3 -m junit2context examples/pytest.xml
```

L'installation utilise actuellement le dépôt Git ; aucune version n'est encore publiée sur PyPI.

Relisez `failures.md` avant de le partager. Vous pouvez ensuite demander à votre assistant :

> Explique les causes probables de ces échecs. Examine le code concerné avant de proposer une correction, puis indique comment la vérifier.

## Fonctionnement

- Lit un ou plusieurs fichiers JUnit XML en UTF-8, y compris les suites imbriquées et les espaces de noms XML.
- Conserve les éléments `<failure>` et `<error>` ; exclut la sortie standard des tests et les propriétés des suites.
- Déduplique les échecs exactement identiques, même présents dans plusieurs fichiers. Les noms de classe font partie de l'identité du test.
- Limite les détails de chaque échec à 2 000 caractères et son message à 500 caractères après masquage, puis ajoute une indication explicite si le texte a été raccourci. Le début et la fin sont conservés pour garder l'exception finale visible.
- Respecte une limite de caractères pour le Markdown, avec des échecs complets et une indication des omissions. Les échecs restent dans l'ordre ; dès qu'un élément ne tient plus, les suivants sont omis.
- Propose une sortie JSON pour les scripts.

```bash
.venv/bin/junit2context examples/pytest.xml --format json --output failures.json
```

Le Markdown utilise une limite de 12 000 caractères par défaut. `--max-chars N` permet de la modifier, avec un minimum de 128 ; cette option est refusée lorsqu'elle est explicitement utilisée avec `--format json`. Une limite en caractères n'est pas une limite en tokens.

`--max-detail-chars N` et `--max-message-chars N` modifient les limites des détails et des messages, en Markdown comme en JSON. `--max-file-bytes N` modifie la taille maximale d'un fichier d'entrée, fixée par défaut à 10 000 000 octets. `--output` remplace un éventuel fichier de sortie existant, mais refuse d'écraser un rapport d'entrée.

Les limites des messages et des détails comptent les caractères conservés après
masquage, sans l'avis de troncature. Si une limite de début ou de fin coupe
`[REDACTED]`, le segment est raccourci pour omettre le marqueur entier, sans
réutiliser l'espace libéré. Un marqueur qui ne tient pas est donc omis en entier.
L'avis compte les caractères du texte masqué réellement supprimés, y compris ceux
des marqueurs omis, et non la longueur du secret d'origine. Cette règle s'applique
en Markdown et en JSON ; le masquage précède toujours la troncature.

Le code de sortie est `0` après une conversion réussie, même si les tests ont échoué. Avec `--fail-on-failures`, il devient `1` en présence d'échecs ou d'erreurs de test. Les erreurs de lecture, d'options ou d'écriture produisent le code `2` et un message sur stderr.

Un rapport annonçant des échecs ou des erreurs sans contenir d'éléments `<failure>` ou `<error>` est refusé comme incomplet.

Les exemples pytest et Vitest sont représentatifs ; ils ne garantissent pas la prise en charge de toutes les versions de ces outils.

## Confidentialité et contributions

Le masquage des secrets repose sur des heuristiques. Il peut manquer des informations sensibles et masquer des textes inoffensifs. **Vérifiez toujours le résultat avant de le partager.** Le contenu des rapports reste une donnée non fiable, pas une instruction à exécuter. Consultez [SECURITY.md](../SECURITY.md).

Pour contribuer, commencez par un rapport XML anonymisé, un test de régression ou une amélioration du résumé. Les étapes se trouvent dans [CONTRIBUTING.md](../CONTRIBUTING.md).

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Projet de [Hafid Idrissi](https://github.com/HafidIdrissi), sous [licence MIT](../LICENSE).

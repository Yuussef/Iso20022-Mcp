# Brouillon de post LinkedIn (français)

> À relire et adapter avec tes mots avant de publier. Remplace [lien démo] et [lien GitHub]. Mets une capture ou le GIF en première image (voir `assets.md`).

---

**Un XSD ISO 20022 valide ne veut pas dire « paiement accepté ».**

En migrant des flux de paiement vers ISO 20022, j'ai vu le même problème revenir : le message passe la validation du schéma, puis il est rejeté ou réparé plus loin dans la chaîne. Les vraies règles, celles de l'EPC pour le SEPA et de CBPR+ pour Swift, ne sont pas dans le XSD.

J'ai donc construit un outil open source qui vérifie ces règles, de façon déterministe et hors ligne :

🇪🇺 **SEPA Credit Transfer** (guides EPC 2025, pacs.008 et pain.001) : euro uniquement, SLEV, IBAN des 41 pays SEPA, jeu de caractères latin, libellé de 140 caractères… et une règle que peu de développeurs connaissent : l'adresse du débiteur devient obligatoire dès qu'une banque suisse ou britannique est dans la chaîne.

🌍 **CBPR+ pacs.008** : une transaction par message, UETR en UUID v4, DEBT/CRED/SHAR, et les décimales ISO 4217 (un montant en JPY avec des centimes est rejeté).

🏠 **Adresses postales** structurées, hybrides ou non structurées. Petite nuance que j'ai vérifiée dans les sources officielles : Swift (27 août 2026) et l'EPC (septembre 2026) ont **reporté** la fin des adresses non structurées prévue en novembre 2026. L'outil le dit, au lieu de répéter une date dépassée.

🔁 **MT103 → pacs.008** : un brouillon de message et un rapport champ par champ qui montre ce qu'un MT103 « ancien » perd en route (pas d'UETR, adresses en texte libre, champ 77B sans équivalent).

🤖 Tout est exposé comme **serveur MCP** : Claude ou un autre agent IA peut appeler ces contrôles et expliquer chaque erreur, sans jamais décider lui-même si un paiement est valide.

Ce que j'en retiens :
• Le travail le plus long a été de **vérifier chaque règle** dans les documents EPC, Swift et SIX, pas d'écrire le code.
• Une IA utile en paiement, c'est une IA **outillée** : des règles déterministes et sourcées, et un modèle qui explique.

Le projet est open source, avec plus de 280 tests et la CI : [lien GitHub]
Démo : [lien démo]

Si tu travailles sur SEPA, CBPR+ ou la migration MT → MX, je suis curieux de savoir quelles règles te posent le plus de problèmes.

#ISO20022 #SEPA #SWIFT #Payments #CBPR #MCP #AI #OpenSource

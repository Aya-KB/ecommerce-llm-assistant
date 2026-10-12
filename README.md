                          DataOlist AI — Assistant intelligent pour l'analyse des données e-commerce

1. Présentation du projet
DataOlist AI est un assistant intelligent basé sur les grands modèles de langage (LLM), conçu pour faciliter l'exploration et l'analyse des données e-commerce à travers des questions formulées en langage naturel.
L'application permet aux utilisateurs de :
- Interroger une base de données sans maîtriser SQL.
- Obtenir des réponses claires et compréhensibles.
- Consulter les résultats sous forme de tableaux.
- Générer automatiquement des visualisations de données.
- Rechercher des informations pertinentes dans des documents grâce à la technologie RAG.
2. Aperçu de l'application
  Interface principale
  <img width="499" height="235" alt="image" src="https://github.com/user-attachments/assets/a1e3e0e0-737c-48a1-b03a-b3cacdf8f9c9" />
  <img width="502" height="246" alt="image" src="https://github.com/user-attachments/assets/4c39a045-e807-4e33-b2bf-b7e832918f19" />
  <img width="586" height="321" alt="image" src="https://github.com/user-attachments/assets/663d480b-c0cf-489c-a0fe-183d0ad5e859" />

3. Fonctionnalités principales
- Interrogation en langage naturel : transformer les questions des utilisateurs en requêtes adaptées à l'analyse des données.
- Analyse des données : explorer les commandes, les clients, les produits, les vendeurs, les paiements et les avis.
- Génération de visualisations : présenter les résultats sous forme de graphiques adaptés aux données.
- Recherche documentaire avec RAG : retrouver des informations pertinentes à partir de documents.
- Interface conversationnelle : interagir avec l'assistant à travers une application web.
- Restitution des résultats : fournir des réponses textuelles, des tableaux et des graphiques.

4. Technologies utilisées
- Langages : Python, JavaScript
- Backend : Flask
- Frontend : React, Vite
- Base de données : PostgreSQL
- Modèle de langage : Llama 3.3 70B Versatile via l'API Groq
- Intelligence artificielle : LLM, génération de requêtes, RAG
- Recherche vectorielle : FAISS
- Traitement des données : Pandas, NumPy
- Visualisation des données : Recharts

5. Architecture du projet
L'application repose sur une architecture composée de plusieurs éléments :
1. Interface utilisateur : l'utilisateur pose une question depuis l'interface web développée avec React.
2. Backend : Flask reçoit la question et déclenche le traitement approprié.
3. Traitement intelligent : l'assistant interprète la demande et identifie les informations nécessaires.
4. Accès aux données : PostgreSQL fournit les données structurées.
5. Recherche documentaire : FAISS permet de retrouver les documents pertinents.
6. Génération de la réponse : le modèle de langage contribue à formuler une réponse en langage naturel.
7. Affichage des résultats : l'interface présente les réponses sous forme de texte, de tableaux ou de graphiques.

6. Structure du projet
ecommerce-llm-assistant/
├── backend/
│   ├── app.py
│   └── chatbot_backend.py
├── frontend/
│   └── src/
├── data/
│   └── documents/
├── faiss_olist_index/
├── .gitignore
└── README.md
Remarque : cette structure est indicative et doit être adaptée à l'organisation réelle du dépôt.

7. Installation et configuration
Prérequis
- Python 3.11
- Node.js et npm
- PostgreSQL
- Une clé API Groq
Étape 1 : Cloner le dépôt
git clone URL_DE_VOTRE_DEPOT
cd ecommerce-llm-assistant
Étape 2 : Configurer l'environnement Python
Créer un environnement virtuel :
python -m venv venv
Sous Windows, activer l'environnement :
.\venv\Scripts\Activate.ps1
Installer les dépendances à partir du fichier de dépendances du projet.
Étape 3 : Configurer les variables d'environnement
Créer un fichier .env contenant les paramètres nécessaires à la connexion à l'API Groq et à la base de données.
Exemple :
GROQ_API_KEY=votre_cle_api
DATABASE_URL=votre_chaine_de_connexion_postgresql
Important : ne jamais publier les clés API, les mots de passe ou les informations confidentielles sur GitHub.
Étape 4 : Lancer le backend
Depuis la racine du projet, exécuter la commande correspondant à la configuration de l'application :
python backend/app.py
Étape 5 : Lancer le frontend
Accéder au dossier frontend :
cd frontend
Installer les dépendances :
npm install
Démarrer l'application :
npm run dev
Ouvrir ensuite l'adresse locale affichée dans le terminal.

8. Jeu de données
Le projet utilise le Brazilian E-Commerce Public Dataset by Olist, un jeu de données public contenant des informations sur :
- Les commandes et les articles commandés.
- Les clients et les vendeurs.
- Les produits et leurs catégories.
- Les paiements.
- Les avis des clients.
Ces données permettent d'explorer différentes dimensions de l'activité e-commerce et de produire des analyses pertinentes.

9. Perspectives d'amélioration
- Améliorer la précision des réponses et des requêtes générées.
- Enrichir les tableaux de bord analytiques.
- Améliorer la qualité de la recherche documentaire.
- Renforcer l'évaluation des réponses et la fiabilité des résultats.
- Étendre les capacités de compréhension multilingue.

10. Auteur
Aya El Kobbi
- Formation : Élève ingénieure en cinquième année en Intelligence Artificielle et Data Science.
- Domaines d'intérêt : Intelligence Artificielle, Machine Learning, Data Science et applications basées sur les LLM.

Projet consacré à l'exploration et à l'analyse intelligente des données e-commerce.

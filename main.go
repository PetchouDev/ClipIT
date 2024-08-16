package main

import (
	// Go standard library packages
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"log"
	"net"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	// Third-party packages (clipboard)
	"golang.design/x/clipboard"

	// Third-party packages (SQLite)

	_ "github.com/mattn/go-sqlite3"
)

// Create a socket object to communicate with the frontend
var socket net.Conn

// Stocker l'état du programme (permet une sortie propre de la boucle de surveillance)
var running bool = true

// Group de synchronisation pour gérer la concurrence
var wg sync.WaitGroup

// Chemin vers le fichier de sauvegarde (défini dans la fonction main mais déclaré en tant que variable globale pour être accessible dans les fonctions)
var dataPath string

// Structure pour stocker les paramètres de l'application
type Settings struct {
	DaysToKeep int `json:"daysToKeep"`
	MaxItems   int `json:"maxItems"`
}

// variable globale pour stocker les paramètres de l'application
var settings Settings

// fonction pour charger les paramètres de l'application
func loadSettings() Settings {
	// Vérifier que le fichier de paramètres existe
	if _, err := os.Stat(filepath.Join(dataPath, "settings.json")); os.IsNotExist(err) {
		// Écrire les paramètres par défaut dans le fichier de paramètres
		err := os.WriteFile(filepath.Join(dataPath, "settings.json"), []byte("{\"daysToKeep\":7,\"maxItems\":100}"), 0644)
		if err != nil {
			log.Fatalf("Impossible d'encoder les paramètres en JSON : %v", err)
		}
	}

	// Lire le contenu du fichier de paramètres
	settingsData, err := os.ReadFile(filepath.Join(dataPath, "settings.json"))
	if err != nil {
		log.Fatalf("Impossible de lire le fichier de paramètres : %v", err)
	}

	// Décoder le contenu du fichier de paramètres
	loadedSettings := Settings{}
	err = json.Unmarshal(settingsData, &loadedSettings)
	if err != nil {
		log.Fatalf("Impossible de décoder le contenu du fichier de paramètres : %v", err)
	}

	println("daysToKeep: ", loadedSettings.DaysToKeep)

	return loadedSettings
}

func ensureDataPath() {
	// Obtenir le répertoire de sauvegarde (%USERPROFILE%\.ClipIT sur Windows, $HOME/.ClipIT sur Linux)
	home, err := os.UserHomeDir()
	if err != nil {
		log.Fatalf("Impossible de trouver le répertoire utilisateur : %v", err)
	}

	// Définir le chemin du fichier de sauvegarde
	dataPath = filepath.Join(home, ".ClipIT")

	// vérifier que le répertoire de fichier de sauvegarde existe
	if _, err := os.Stat(dataPath); os.IsNotExist(err) {
		os.MkdirAll(dataPath, os.ModePerm)

		// Si le système d'exploitation est Windows, cacher le répertoire
		if runtime.GOOS == "windows" {
			err = os.Chmod(dataPath, 0777)
			if err != nil {
				log.Fatalf("Impossible de cacher le répertoire de sauvegarde : %v", err)
			}
			err = syscall.SetFileAttributes(syscall.StringToUTF16Ptr(dataPath), syscall.FILE_ATTRIBUTE_HIDDEN)
			if err != nil {
				log.Fatalf("Impossible de cacher le répertoire de sauvegarde : %v", err)
			}
		}
	}

	// Vérifier que la base de données SQLite existe, la créer et créer la table si elle n'existe pas
	db, err := sql.Open("sqlite3", filepath.Join(dataPath, "clipboard.db"))
	if err != nil {
		log.Fatalf("Impossible de créer la base de données : %v", err)
	}

	_, err = db.Exec("CREATE TABLE IF NOT EXISTS clipboard (id INTEGER PRIMARY KEY, type TEXT, data TEXT, date TEXT, filepath TEXT)")
	if err != nil {
		log.Fatalf("Impossible de créer la table : %v", err)
	}

	// Fermer la connexion à la base de données
	err = db.Close()
	if err != nil {
		log.Fatalf("Impossible de fermer la connexion à la base de données : %v", err)
	}

	// Vérifier que le répertoire de cache des images existe
	if _, err := os.Stat(filepath.Join(dataPath, "tmp")); os.IsNotExist(err) {
		os.MkdirAll(filepath.Join(dataPath, "tmp"), os.ModePerm)
	}
}

// Check if a string represents a color
func isColor(s string) bool {
	return regexp.MustCompile(`^#([0-9A-Fa-f]{3}){1,2}$`).MatchString(s) || regexp.MustCompile(`^#([0-9A-Fa-f]{4}){1,2}$`).MatchString(s) || regexp.MustCompile(`^rgb\(\d{1,3},\d{1,3},\d{1,3}\)$`).MatchString(s) || regexp.MustCompile(`^rgba\(\d{1,3},\d{1,3},\d{1,3},\d?\.?\d+\)$`).MatchString(s) || regexp.MustCompile(`^hsl\(\d{1,3},\d{1,3}%,\d{1,3}%\)$`).MatchString(s) || regexp.MustCompile(`^hsla\(\d{1,3},\d{1,3}%,\d{1,3}%,\d?\.?\d+\)$`).MatchString(s)
}

// fonction de surveillance du presse-papiers
func clipboardWatcher(ctx context.Context) {

	// Créer un canal pour recevoir les images du presse-papiers
	imageChannel := clipboard.Watch(ctx, clipboard.FmtImage)

	// Créer un canal pour recevoir les textes du presse-papiers
	textChannel := clipboard.Watch(ctx, clipboard.FmtText)

	// Variables pour stocker les denières copies du presse-papiers et éviter les doublons
	var lastImage [32]byte = sha256.Sum256([]byte{})
	var lastText string = ""

	// Ouvrir une connexion à la base de données SQLite
	db, err := sql.Open("sqlite3", filepath.Join(dataPath, "clipboard.db"))
	if err != nil {
		log.Fatalf("Impossible d'ouvrir la base de données : %v", err)
	}

	// Fermer la connexion à la base de données à la fin de la fonction
	defer db.Close()

	// boucle de surveillance
	println("Démarrage de la surveillance du presse-papiers...")

	for running {
		println(running)
		// Sélectionner le canal qui a reçu le dernier élément du presse-papiers
		select {
		case <-ctx.Done():
			println("Arrêt de la surveillance du presse-papiers.")
			wg.Done()
			return

		// Cas où une image a été copiée
		case image := <-imageChannel:
			// Vérifier si l'image copiée est la même que la dernière image copiée
			if sha256.Sum256(image) == lastImage {
				continue
			}

			// Obtenir le timestamp unix actuel
			timestamp := int64(time.Now().Unix())

			// Créer un nom de fichier unique pour l'image (les 8 premiers caractères du checksum SHA256 de l'image + le timestamp unix)
			fileSha256 := sha256.Sum256(image)

			// Convertir le checksum SHA256 en hexadécimal
			fileName := make([]byte, hex.EncodedLen(len(fileSha256)))
			hex.Encode(fileName, fileSha256[:])

			fileNameString := base64.URLEncoding.EncodeToString(fileName)
			fileNameString = string(fileNameString)[:20] + strconv.FormatInt(timestamp, 10)[5:] + ".png"

			// Écrire l'image dans un fichier
			err := os.WriteFile(filepath.Join(dataPath, "tmp", fileNameString), image, 0644)
			if err != nil {
				log.Fatalf("Impossible d'écrire l'image dans un fichier : %v", err)
			}

			// Insérer l'image dans la base de données
			_, err = db.Exec("INSERT INTO clipboard (type, data, date, filepath) VALUES (?, ?, ?, ?)", "image", fileNameString, timestamp, filepath.Join(dataPath, "tmp", fileNameString))
			if err != nil {
				log.Fatalf("Impossible d'insérer l'image dans la base de données : %v", err)
			}

			println("Image copiée : ", fileNameString)

		// Cas où un texte a été copié
		case text := <-textChannel:
			// Convertir les bytes en string
			textString := string(text)

			// Supprimer les caractères vides en fin de texte
			textString = strings.TrimRight(textString, "\n\r ")

			// Vérifier si le texte copié est le même que le dernier texte copié ou si le texte copié est vide
			if textString == lastText || textString == "" {
				continue
			}

			// Déterminer si le texte copié est une URL (http:// ou https://), une couleur (#RRGGBB, #RGB, #RRGGBBAA ou #RGBA, rgb(), rgba(), hsl() ou hsla()), un mail (user@domain) ou un texte normal
			dataType := "text"

			// If the text is a URL
			if strings.HasPrefix(textString, "http://") || strings.HasPrefix(textString, "https://") || strings.HasPrefix(textString, "mailto://") {
				dataType = "url"

				// If the text is a color (check with raw copy and with all blank spaces removed)
			} else if isColor(textString) || isColor(strings.ReplaceAll(strings.Trim(textString, " \n\r"), " ", "")) {
				dataType = "color"
				textString = strings.ReplaceAll(strings.Trim(textString, " \n\r"), " ", "")
			} else if regexp.MustCompile(`^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`).MatchString(textString) {
				dataType = "mail"
			}

			// Obtenir le timestamp unix actuel
			timestamp := int64(time.Now().Unix())

			// Insérer le texte dans la base de données
			_, err = db.Exec("INSERT INTO clipboard (type, data, date) VALUES (?, ?, ?)", dataType, textString, timestamp)
			if err != nil {
				log.Fatalf("Impossible d'insérer le texte dans la base de données : %v", err)
			}

			println("Texte copié : ", textString, " (", dataType, ")")

		}
	}

	println("Arrêt de la surveillance du presse-papiers.")

	// Attendre que la goroutine se termine
	wg.Done()
}

func deleteOldItems() {
	// Supprimer les éléments de l'historique du presse-papiers qui sont plus anciens que le nombre de jours à conserver

	// TODO: Implémenter la suppression des éléments de l'historique du presse-papiers qui sont plus anciens que le nombre de jours à conserver
}

/* // Handle the frontend connection
func HandleFrontendConnection() {
	// While the frontend is connected, check if it has sent an id of an item to push to the clipboard
	for {
		// Check if the frontend is still connected
		_, err := socket.Write([]byte("ping"))
		if err != nil {
			println("Frontend disconnected.")
			return
		}

		// Wait a bit before checking again (to avoid high CPU usage)
		time.Sleep(10 * time.Millisecond)
	}
} */

func main() {
	// Vérifier que le répertoire de sauvegarde existe, le créer s'il n'existe pas et attribuer le chemin du fichier de sauvegarde
	ensureDataPath()

	// Initialiser le presse-papiers
	err := clipboard.Init()
	if err != nil {
		log.Fatalf("Impossible d'initialiser le presse-papiers : %v", err)
	}

	// Charger les paramètres de l'application
	settings = loadSettings()

	// Supprimer les éléments de l'historique du presse-papiers qui sont plus anciens que le nombre de jours à conserver
	deleteOldItems()

	// Créer un contexte pour recevoir les événements du presse-papiers
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Se placer dans le répertoire du programme
	err = os.Chdir(filepath.Dir(os.Args[0]))
	if err != nil {
		log.Fatalf("Impossible de se placer dans le répertoire du programme : %v", err)
	}

	// Get the absolute path of the executable directory
	absPath, err := filepath.Abs(os.Args[0])
	if err != nil {
		log.Fatalf("Impossible d'obtenir le chemin absolu du répertoire de l'exécutable : %v", err)
	}

	// Démarrer la surveillance du presse-papiers dans une goroutine
	wg.Add(1)
	go clipboardWatcher(ctx)

	// Lancer l'interface graphique et attendre qu'elle se ferme
	cmd := exec.Command(path.Join(filepath.Dir(absPath), "frontend.exe"))
	output, cmd_err := cmd.Output()
	if cmd_err != nil {
		log.Fatalf("Une erreur est survenu avec l'interface : %v", cmd_err)
	}

	println("Output: ", string(output))

	// Quand l'interface graphique est fermée, stopper la surveillance du presse-papiers
	running = false
	cancel()
	wg.Wait()

	// Quitter le programme
	println("Arrêt du programme.")
	return
}

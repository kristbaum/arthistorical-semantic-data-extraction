cat > test_mistral.py << 'EOF'
#!/usr/bin/env python3
import requests
import json

def test_ollama_connection():
    """Test if Ollama is running and can process text"""
    try:
        # Test connection to Ollama
        response = requests.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            print("✓ Ollama is running")
            models = response.json().get('models', [])
            print(f"Available models: {[m['name'] for m in models]}")
            return True
        else:
            print("✗ Ollama not responding")
            return False
    except Exception as e:
        print(f"✗ Error connecting to Ollama: {e}")
        return False

def format_and_clean_text(text, model="mistral:7b"):
    """Test function to format and clean art historical text using Mistral"""
    
    prompt = f"""
    Clean and format this scanned German art historical text about baroque ceiling paintings. Fix line breaks, obvious OCR errors and remove random, wrongly scanned headlines, text from maps or artwork, or image captions in the text. Export the text as Markdown and use bold text for parts before ":". Don't add any new text, stay close to the original, only format it for online publishing.
    
    Text to clean and format:
    {text}
    
    Cleaned text:
    """
    
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,  # Lower temperature for consistent formatting
                    "top_p": 0.9
                }
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['response']
        else:
            return f"Error: {response.status_code}"
            
    except Exception as e:
        return f"Error: {e}"

# Test the setup
if __name__ == "__main__":
    print("Testing Mistral setup on LRZ...")
    
    if test_ollama_connection():
        # Sample messy art historical text that needs formatting
        sample_text = """
        LANDKREIS LANDSBERG AM LECH


ADELSHAUSEN


Kapelle in Privatbesitz, Gemeinde Weil, Pfarrei Beuer-
bach, Diözese Augsburg; z. Z. der Ausmalung hatte
Kloster Benediktbeuern das Präsentationsrecht auf die
Pfarrei, Gericht Landsberg
Patrozinium: St. Martin
Zum Bauwerk: Die Jahreszahl 1677 (mit den Namen Be¬
nediktus Fichtell, Jakob Fichtell) im Giebel der Westfront
ist wohl auf Baumaßnahmen an dem im Kern spätgotischen
Kapellenbau zu beziehen. – Die Kapelle hat einen ein¬
fachen rechteckigen Gemeinderaum und einen leicht ein¬
gezogenen querrechteckigen Altarraum.


Autor und Entstehungszeit: Die Deckenbilder zeigen trotz
ihres schlechten Zustandes so große Ähnlichkeit mit den
Fresken Johann Baptist Anwanders, daß man sie dem
Augsburger Meister zuschreiben muß. Die beiden Wand-
bilder (Wi-2) mit dem hl. Joseph und besonders die Er-
ziehung Mariens durch Anna kehren wenig variiert im AR
von Hausen bei Geltendorf und in Eresried (OB, LKr.
Fürstenfeldbruck) wieder. Der Typus des heiligen Bischofs
in B ist auch von anderen Anwanderfresken her bekannt:
Hausen bei Geltendorf (Presko B), Hechenwang (Fresko
C), St. Ulrich bei Egling (Fresko A). Auch die Figuren von
A und Ai-4 entsprechen dem Malstil Anwanders. Auf
Grund des stilistischen Befundes sind die Adelshausener
Kapellenfresken in zeitliche Nähe zu den signierten und
datierten Fresken von 1795 in der Pfarrkirche von Hausen
bei Geltendorf zu setzen (Angaben zur Biographie des
Malers siehe dort).


Befund
Träger der Deckenmalerei: LHs Flachdecke, AR Kreuz-
rippengewölbe
Rahmen: A Stuckprofil, B gemaltes Profil, von Rocaille¬
formen überspielt
Technik: Fresko; polychrom
Maße: A Höhe 3,30 m; 1,75 X 1,40
B Höhe 3,45 m; 1,00 X 1,30
Erhaltungszustand und Restaurierungen: Der Erhaltunge¬
zustand ist sehr schlecht, die Bilder sind teilweise zerstört,
die Farben zersetzt. In A Fehlstelle am rechten Bildrand,
am linken schadhaft; Az große Fehlstelle, As völlig, A4
weitgehend ruiniert. Durch Übermalung entstellt ist das
Mittelbild A; die Wandbilder Wi-2 im AR sind gleich-
falls übermalt. Wenig beeinträchtigt durch Übermalung
und Schäden ist das AR-Fresko B.
Beschreibung und Ikonographie
A MANTELSPENDE DES LL. MARTIN Die belieb¬
te Legende aus dem Leben des Heiligen wird in einer


A Mantelspende des hl. Martin
tafelbildmäßigen Anlage mit geringer Untersicht veran¬
schaulicht, die durch eine terrestrische Vordergrundsrampe
auf Tiefenwirkung berechnet ist. St. Martin auf dem Roß
und der Bettler erscheinen in einer Landschaft, in deren
Hintergrund eine Burg aufragt; Putti über dem Heiligen
tragen seine Bischofsinsignien.
B ST. MARTIN IN DER GLORIE Der Heilige thront
auf Wolken, die Rechte zum Segensgestus vor die Brust
erhoben, den Blick aufwärts gerichtet. Im Arm hält er den
Bischofsstab, neben ihm liegen auf einer Wolke Mitra,
Buch und sein spezielles Attribut, die Gans.
B St. Martin in der Glotie


ADELSHAUSEN
AI-1 ALLEGORISCHEDARSTELLUNGEN Dictrag
meniarisch erhaltenen Zwickelbilder im Langhaus lassen
Bildfiguren erkennen, die vermutlich als die Vier Letzten
Dinge zu deuten sind
Al (keine Abbildung) Von einer verhüllten Figur in
der Mitte des Bildes sind ein Skelettarm mit einem läng-
lichen Gegenstand in der Skeletthand rechts im Bild sowie
die zweite Skeletthand vor den Tuchfalten erkennbar
Links im Bild windet sich über einem ein wenig geöffneten
Sarkophag (vgl. die Bildformen in As) eine Schlange mit
einem Apfel im Maul um die Weltkugel (oder Konvex¬
spiegel?). Die verhüllte Skelettgestalt ist wohl als Tod
anzusprechen, die Schlange mit dem Apfel soll auf den
ursächlichen Zusammenhang von Sünde und Tod, die
durch den Teufel in die Welt kamen, hinweisen
A2 Ein Engel bläst die Posaune, daran hängt eine Fahne
gewiß (vgl. dazu die ikonographischen Angaben für das
mit dem Gerichtssymbol der Waage. Am unteren Bild-
rand stemmt eine verhüllte Menschengestalt offenbar ei¬
nen Sargdeckel hoch (= Gericht).
.
S.
—
Al Hi


le
Garmisch-Partenkirchen, s. Bd 2); doch wäre bei einem
Fresko des Matthäus Günther in Garnisch, OB, LKr.
erschien ihm der Teufel, doch er war sich des Paradieses
St. Martin sah seinen Tod voraus, an seinem Totenbett
Diese sind vielleicht sinngemäß auf St. Martin zu beziehen
die Vier Letzten Dinge: Tod, Gericht, Himmel und Hölle.
mes. Hinzugeordnet sind allegorische Darstellungen, wohl
Glorifikation des hl. Martin im Mittelpunkt des Program-
Dem Patron der Kirche entsprechend stehen Leben und
in Flammen (?), von Teufelskrallen erfaßt (= Hölle).
As (keine Abbildung) Reste einer menschlichen Gestalt
len auf den jüngling herab (= Himmel).
nete Dreieck der Dreifaltigkeit. Von diesem fallen Strah
lichten Gloriole erscheint das durch drei Flammen bezeich¬
ruht ein Putto mit einem Palmkranz in der Hand. In einer
gebreiteten Armen und erhobenem Blick; zu seiner Seite
Ai Auf Wolken liegender halbnackter Jüngling mit aus¬


Wi St.
#


ADELSHAUSEN
solchen Sinnbezug im Hauptbild eher die Darstellung des
Todes des Heiligen als dessen Mantelspende zu erwarten.
Das aus dem Katechismus stammende Bildtherna der Vier
Letzten Dinge finder sich vereinzelt in der barocken Decken¬
malerei in Deutschland (vgl. Andor Pigler, Barockthemen,
Bd 1, Budapest 1956, S. 534; MDK, Bd 4, Sp. 12—22, s. v.
Dinge, Vier Letzte).
Die Wandfresken befinden sich an der N- und S- Wand
des Altarraumes.
Wi S./JOSEPH Der Heilige in der Zimmermannswerk¬
statt; das Jesuskind kehrt Hobelspäne.
W2 S./ANNA Vor seiner Mutter Anna kniet lesend das
Mädchen Maria.
Literatur
Müller-Hahl, Bernhard (Hg.), Heimatbuch Stadt- und
Landkreis Landsberg am Ledi, Aßling-München 1966,
S. 102 f.
        """
        
        print("\nOriginal text:")
        print(sample_text)
        print("\nCleaning and formatting text...")
        result = format_and_clean_text(sample_text)
        print("\nFormatted output:")
        print(result)
    else:
        print("Please start Ollama first: ollama serve &")
EOF
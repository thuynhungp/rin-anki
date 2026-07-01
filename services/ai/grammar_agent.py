from PIL import Image
from services.ai.gemini import GeminiVocabularyExtractor

class GrammarAgent:
    def __init__(self):
        self.extractor = GeminiVocabularyExtractor()

    def process_note_with_vocab(self, image: Image.Image, session, user_id: int) -> str:
        # Fetch vocabulary from the user's latest KR deck
        from services.database import User
        user = session.get(User, user_id)
        known_words = []
        if user:
            kr_decks = [d for d in user.decks if d.language == "KR"]
            # Sort by id descending to get the latest deck first
            kr_decks.sort(key=lambda d: d.id, reverse=True)
            if kr_decks:
                latest_deck = kr_decks[0]
                for vocab in latest_deck.vocabulary:
                    known_words.append(vocab.word.strip())
        
        # Call the extractor with the known vocabulary words
        return self.extractor.extract_grammar_note(image, known_words=known_words)

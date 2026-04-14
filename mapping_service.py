import os
import gspread
from rapidfuzz import process, fuzz
from typing import Optional, List, Dict

class MappingService:
    def __init__(self, google_sheet_url: str, credentials_file: str):
        self.sheet_url = google_sheet_url
        self.credentials_file = credentials_file
        self.mapping_data: List[Dict] = []
        self.legal_names: List[str] = []
        self.brand_names: List[str] = []
        self._load_data()

    def _load_data(self):
        """Loads branding data from the first sheet or a sheet named 'Справочник'."""
        try:
            client = gspread.service_account(filename=self.credentials_file)
            sh = client.open_by_url(self.sheet_url)
            
            # Try to find a sheet with mapping, or use the first one
            try:
                worksheet = sh.worksheet("Sheet1") # As seen in screenshot
            except:
                worksheet = sh.get_worksheet(0)
            
            # Expected columns: ИМЯ, АЛЬФА ИМЯ, КАТЕГОРИЯ, ПОДКАТЕГОРИЯ
            raw_data = worksheet.get_all_values()
            if len(raw_data) > 1:
                headers = raw_data[0]
                data = [dict(zip(headers, row)) for row in raw_data[1:]]
            else:
                data = []
            
            self.mapping_data = data
            
            # Pre-populate lists for fuzzy matching
            self.legal_names = [str(row.get('АЛЬФА ИМЯ', '')).strip() for row in data if row.get('АЛЬФА ИМЯ')]
            self.brand_names = [str(row.get('ИМЯ', '')).strip() for row in data if row.get('ИМЯ')]
            
            print(f"MappingService: Loaded {len(self.mapping_data)} records.")
        except Exception as e:
            print(f"MappingService Error loading data: {e}")

    def find_mapping_by_legal_name(self, legal_name_on_receipt: str, threshold: int = 80) -> Optional[Dict]:
        """Fuzzy matches a legal name from a receipt to the mapping table."""
        if not self.legal_names or not legal_name_on_receipt:
            return None
        
        # legal_name_on_receipt: e.g. "PROWEB MCHJ"
        # self.legal_names: e.g. ["OOO PROWEB", "ANGLESEY FOOD"]
        
        result = process.extractOne(
            legal_name_on_receipt, 
            self.legal_names, 
            scorer=fuzz.partial_ratio # Good for "MCHJ" vs "OOO" cases
        )
        
        if result:
            match_name, score, index = result
            if score >= threshold:
                # Find the original row
                for row in self.mapping_data:
                    if str(row.get('АЛЬФА ИМЯ', '')).strip() == match_name:
                        print(f"Mapping match: '{legal_name_on_receipt}' -> '{match_name}' (Score: {score})")
                        return row
        return None

    def search_by_brand_name(self, query: str, threshold: int = 70) -> List[Dict]:
        """Wrapper for search_by_field to maintain compatibility."""
        return self.search_by_field('ИМЯ', query, threshold)

    def search_by_field(self, field_name: str, query: str, threshold: int = 70) -> List[Dict]:
        """Generic search for all records associated with a field value."""
        if not query or not self.mapping_data:
            return []
        
        # Get all unique values for the specified field
        field_values = [str(row.get(field_name, '')).strip() for row in self.mapping_data if row.get(field_name)]
        if not field_values:
            return []

        # Find best matches in the specified field
        matches = process.extract(
            query, 
            field_values, 
            limit=10, 
            scorer=fuzz.WRatio
        )
        
        results = []
        seen_matches = set()
        
        for match_val, score, index in matches:
            if score >= threshold and match_val not in seen_matches:
                seen_matches.add(match_val)
                # Find all rows matching this value
                for row in self.mapping_data:
                    if str(row.get(field_name, '')).strip() == match_val:
                        results.append(row)
        
        return results

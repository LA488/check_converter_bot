import os
import gspread
from rapidfuzz import process, fuzz
from typing import Optional, List, Dict # Critical for server-side compatibility


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
            print(f"MappingService: Sample brands: {self.brand_names[:10]}")
            print(f"MappingService: Available columns: {list(data[0].keys()) if data else 'No data'}")
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

    def search_by_brand_name(self, query: str, threshold: int = 60) -> List[Dict]:
        """Wrapper for search_by_field to maintain compatibility. Lower threshold for better results."""
        return self.search_by_field('ИМЯ', query, threshold)

    def search_by_field(self, field_name: str, query: str, threshold: int = 70) -> List[Dict]:
        """Generic search for all records associated with a field value."""
        if not query or not self.mapping_data:
            print(f"[SEARCH] Empty query or no data. Query: '{query}', Data count: {len(self.mapping_data)}")
            return []

        # Normalize query to lowercase for case-insensitive search
        query_lower = query.lower().strip()

        # Get all unique values for the specified field (lowercase for comparison)
        field_values = []
        field_values_original = {}  # Map lowercase -> original

        for row in self.mapping_data:
            value = str(row.get(field_name, '')).strip()
            if value:
                value_lower = value.lower()
                field_values.append(value_lower)
                field_values_original[value_lower] = value

        print(f"[SEARCH] Field '{field_name}': found {len(field_values)} values")
        if not field_values:
            print(f"[SEARCH] No values found for field '{field_name}'")
            print(f"[SEARCH] Available fields in first row: {list(self.mapping_data[0].keys()) if self.mapping_data else 'No data'}")
            return []

        # Find best matches in the specified field (case-insensitive)
        matches = process.extract(
            query_lower,
            field_values,
            limit=10,
            scorer=fuzz.WRatio
        )

        print(f"[SEARCH] Query '{query}' found {len(matches)} matches")
        if matches:
            print(f"[SEARCH] Top 3 matches: {[(m[0], m[1]) for m in matches[:3]]}")

        results = []
        seen_matches = set()

        for match_val_lower, score, index in matches:
            if score >= threshold and match_val_lower not in seen_matches:
                seen_matches.add(match_val_lower)
                # Get original value (with correct case)
                original_val = field_values_original.get(match_val_lower, match_val_lower)
                # Find all rows matching this value (case-insensitive)
                for row in self.mapping_data:
                    row_val = str(row.get(field_name, '')).strip()
                    if row_val.lower() == match_val_lower:
                        results.append(row)

        print(f"[SEARCH] Returning {len(results)} results (threshold: {threshold})")
        return results

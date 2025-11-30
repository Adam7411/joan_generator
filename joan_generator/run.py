# ... (początek pliku bez zmian) ...

# W funkcji index(), w pętli layout_rows:
                for row in layout_rows:
                    if not row: continue
                    row_parts = []
                    for w in row:
                        widget_str = w['id']
                        
                        # --- FIX: Zapewnienie, że rozmiar jest dodawany czysto ---
                        size = w.get('size', '').strip()
                        if size:
                            # Upewnij sie, ze rozmiar ma nawiasy, ale nie dubluj ich
                            if not size.startswith('('): size = f"({size})"
                            widget_str += size
                            
                        row_parts.append(widget_str)
                    
                    row_str = ", ".join(row_parts)
                    generated_yaml += f"  - {row_str}\n"
                    processed_widgets.extend(row)

# ... (reszta pliku bez zmian) ...

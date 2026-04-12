import requests
import xml.etree.ElementTree as ET
import random

class FutoshikiFetcher:
    BASE_URL = "https://www.futoshiki.com/get.cgi"
    
    HEADERS = {
        "accept": "*/*",
        "accept-language": "vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5",
        "sec-ch-ua": "\"Chromium\";v=\"146\", \"Not-A.Brand\";v=\"24\", \"Google Chrome\";v=\"146\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "cookie": "_ga=GA1.1.698886926.1774260194; _ga_SJ12DKC7XE=GS2.1.s1775631511$o3$g1$t1775631921$j37$l0$h0",
        "Referer": "https://www.futoshiki.com/"
    }
    
    @staticmethod
    def fetch_puzzle(size=4, difficulty=1, game_id=None):
        """
        Fetch Futoshiki puzzle từ futoshiki.com
        
        Args:
            size: Size của puzzle (4-9)
            difficulty: Độ khó (0-3)
            game_id: ID của puzzle, nếu None thì random (0-9999)
            
        Returns:
            dict: {size, board, answer, constraints}
        """
        if game_id is None:
            game_id = random.randint(0, 9999)
        
        params = {
            "size": size,
            "difficulty": difficulty,
            "id": game_id
        }
        
        try:
            response = requests.get(FutoshikiFetcher.BASE_URL, params=params, headers=FutoshikiFetcher.HEADERS)
            response.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(response.content)
            
            # Lấy dữ liệu game - có thể root là <game> hoặc root có chứa <game>
            if root.tag == 'game':
                game_data = root.text
            else:
                game_element = root.find('game')
                if game_element is None:
                    print(f"Lỗi: Không tìm thấy tag 'game'")
                    return None
                game_data = game_element.text
            
            if game_data is None:
                print(f"Lỗi: Tag 'game' rỗng")
                return None
            
            # Parse game data
            board, answer, constraints = FutoshikiFetcher.parse_game_data(game_data, size)
            
            return {
                "size": size,
                "board": board,
                "answer": answer,
                "constraints": constraints
            }
        except ET.ParseError as e:
            print(f"Lỗi parse XML: {e}")
            print(f"Response: {response.text}")
            return None
        except Exception as e:
            print(f"Lỗi khi fetch puzzle: {e}")
            return None
    
    @staticmethod
    def parse_game_data(game_str, size):
        """
        Parse game string từ XML
        
        Format mỗi dòng có độ rộng 2*size-1 ký tự.
        Dòng chẵn (0,2,4,...) trong phần board: cells + horizontal constraints
        Dòng lẻ (1,3,5,...) trong phần board: vertical constraints
        
        Args:
            game_str: Chuỗi dữ liệu game
            size: Kích thước board (4-9)
            
        Returns:
            tuple: (board, answer, constraints)
        """
        line_width = 2 * size - 1

        # Tách thành các dòng theo đúng độ rộng của board
        lines = []
        for i in range(0, len(game_str), line_width):
            lines.append(game_str[i:i + line_width])
        
        # Board và answer đều có 2*size-1 dòng
        total_board_lines = line_width
        board_lines = lines[:total_board_lines]
        answer_lines = lines[total_board_lines:total_board_lines * 2]

        # Parse board
        board = []
        constraints = []
        
        # Dòng chẵn trong board_lines là cells
        for row_idx in range(0, len(board_lines), 2):
            line = board_lines[row_idx]
            row = []
            for col_idx, char in enumerate(line):
                if col_idx % 2 == 0:  # Cell positions
                    if char == '.':
                        row.append(0)
                    elif char.isdigit():
                        row.append(int(char))
                    elif char == '_':
                        row.append(0)
                else:  # Horizontal constraint positions
                    cell1_col = col_idx // 2
                    cell2_col = col_idx // 2 + 1
                    actual_row = row_idx // 2
                    
                    if char == '(':
                        constraints.append(((actual_row, cell1_col), (actual_row, cell2_col)))
                    elif char == ')' or char == '>':
                        constraints.append(((actual_row, cell2_col), (actual_row, cell1_col)))
            
            if row:
                board.append(row)

        if any(len(row) != size for row in board):
            raise ValueError(f"Board parse failed: expected {size} columns, got {[len(row) for row in board]}")

        # Dòng lẻ trong board_lines là vertical constraints
        for line_idx in range(1, len(board_lines), 2):
            line = board_lines[line_idx]
            for col_idx, char in enumerate(line):
                if col_idx % 2 == 0:  # Vertical constraint positions
                    actual_col = col_idx // 2
                    actual_row = line_idx // 2
                    
                    if char == '^':
                        constraints.append(((actual_row, actual_col), (actual_row + 1, actual_col)))
                    elif char == 'v':
                        constraints.append(((actual_row + 1, actual_col), (actual_row, actual_col)))
        
        # Parse answer
        answer = []
        for row_idx in range(0, len(answer_lines), 2):
            if row_idx >= len(answer_lines):
                break
            line = answer_lines[row_idx]
            row = []
            for col_idx, char in enumerate(line):
                if col_idx % 2 == 0:  # Cell positions
                    if char.isdigit():
                        row.append(int(char))
                    else:
                        row.append(0)
            if row:
                answer.append(row)
        
        return board, answer, constraints


if __name__ == "__main__":
    # Test
    puzzle = FutoshikiFetcher.fetch_puzzle(size=6, difficulty=2, game_id=6767)
    if puzzle:
        print(f"Board:")
        for row in puzzle['board']:
            print(row)
        print(f"\nAnswer:")
        for row in puzzle['answer']:
            print(row)
        print(f"\nConstraints:")
        print(puzzle['constraints'])

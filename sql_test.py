import sqlite3

# DB 파일 연결
conn = sqlite3.connect("database.db")

# 커서 생성
cur = conn.cursor()

# 테이블 조회
cur.execute("SELECT * FROM ticker")

# 결과 출력
rows = cur.fetchall()
for row in rows:
    print(row)

# 연결 종료
conn.close()

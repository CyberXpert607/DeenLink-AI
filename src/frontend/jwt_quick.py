import jwt
from datetime import datetime, timedelta

privaete_key = """-----BEGIN PRIVATE KEY-----
MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDeIOhT/kNCH/Q4
qTwon/Ltf8Gb12kuyWk3AGYhQBrDW7hyk3uPV6axKBYPic/G9ydiQsz9hNubvZiY
7v1cprUX81i4l3AnRfGtVSI8vCXdiNG2NXOjZrMCJkGwTzJ86dATK97pMFwjr3Or
9oYLlstGciYKzom0mqxCgatMD9EXkj74Go/f6K4JqZAGpFYNP8ulapf7W2KafIt4
qxypTo4ZpeUSK5kmvf/TsBh0OBA68BB3NzshR7WonAQg9DM+fpLyIzAJVcDPgHhb
G7QYGtT0p8cm6YYSTlNQBc4WHxfOjsDAy+IJQfuXh9DDXtvqkKfHFgBYjheQ5+e3
FOiBOKNpAgMBAAECggEAEw/P4CVZsDr9wj8DopjXR/pGqxD5PcKa/NVT7laJ9WnR
kkOFvu9OprVB72NsKS7celoxLTBRiDPk/HrF00WbFMsVOgIE5dniu3Uq0vtyZGhx
VqmPmt4dTnnp+S9SrdWCvaJuJqS3w3gy/PbS2fu+xfTVvueqeY0sayilgol48AS7
5GB8QgtuwVMvtwbKwuWXijjGgYpQzq1o2SKmBfjBqMvGFendi26c8v/VmtrHup9M
Tn25foFs9uzrmCLld40dyWrxBq02eJHdher62hzema/HIYIGI1PZe7jJemjp9dzi
AAKrnsFFXYHoZWIz57fH10D3iSX7aPTXfpU4oHidgQKBgQDxU9SZj/WirUELawPd
Kk85CyaOGj9+NLiWrDjofrwXtBj+X6vXCXX4GbldiqCC6EDG+CYpJo5gtcs2KLTZ
4SvdistYtIGnEmv+XvBjIjR6r2jtrByucoDZp52g0YOhe72bvzRpVjSE0M9GGaU7
9idRUnVTcULIbYTSPefbhUH6VQKBgQDrokDVyZc9wwLfLnLfIwPDCyOYhatDCEJW
0npA4ik9J2WfnEm0w4KkPTSb1kY6agjq6sOBlP3/uHcbqx2Xhf2eKiHVzRRSSIkX
rGWLuLwUDffNZ3KMXW+rM8ZBg9xyX51w5D8uWOJOaSqd/tGZrTvWrn3FkdTAcDZF
v/imCKcAxQKBgGun7gujQP0VNRMW5l5fZYAZDVYPN4vhkQcGRUzSXK5mVVAE9e+z
9MB9GUg1c21ylpMsWDm7TYCvGLxMZIFeBeeK5zPnMn+JpEuRpsNSmv6wCasdQJ5B
zmFKePMpBAOh4+/62DK1ljA5xn2LKz8YjGmm01gqCpTG5p2zqB8xz0ERAoGAWpcq
rgau6sPKmttUtozTqWzi5oSdb0wBlTeeYMuSZzx6SX7gp2pzE4mkbDVZEqQpgYd4
Wp1ZebMFt9F1sweElgZEs9oAchIJAtz4vVrslBk6p/GZjHVvtTZWhmGXozE3amuW
Ds+FUfgEtnF9S8PaOZMkL4z9am65rt87TToOWrECgYBLgEslRqu6ZViBVqPjlVLA
7x+5eaGTX2zpxDPE0EH0J+4Z6AnsyTKQpW/eqxFrBKSwOQBJ+hnX6aTqQZoMPEOb
Sm7or9fcSvJ5gfGv0y0IsTT4lC7ldIQ3X4o8zdaI3Lu7k4h7IBEXAhnv4sXRnHzO
hYNUKWJ6/TQPPuPup8z26w==
-----END PRIVATE KEY-----
"""
payload= {
    "sub": "1234567890",
    "username": "test_user",
    "user_type": "admin",
    "iss": "deenlink",
    "aud": "deenlink-ai",
    "exp": datetime.utcnow() + timedelta(hours=2)
}
token = jwt.encode(payload, privaete_key, algorithm="RS256")
print(token)
from app import app

with app.test_client() as c:
    with c.session_transaction() as s:
        s['otp_flow'] = 'forgot'
        s['forgot_verified'] = True
        s['otp_meta'] = {'email': 'y0263320@gmail.com'}

    page = c.get('/reset-password')
    print('GET /reset-password status:', page.status_code)
    print('GET /reset-password has form:', 'new_password' in page.get_data(as_text=True) and 'confirm_password' in page.get_data(as_text=True))

    post = c.post('/reset-password', data={
        'new_password': 'Reset1234',
        'confirm_password': 'Reset1234',
    }, follow_redirects=False)
    print('POST /reset-password status:', post.status_code)
    print('POST /reset-password location:', post.headers.get('Location'))

from app import app

with app.test_client() as c:
    with c.session_transaction() as s:
        s['otp_flow'] = 'forgot'
        s['forgot_verified'] = True
        s['otp_meta'] = {'email': 'y0263320@gmail.com'}

    page = c.get('/reset-password')
    print('status', page.status_code)
    print('location', page.headers.get('Location'))
    body = page.get_data(as_text=True)
    print('contains_new_password', 'new_password' in body)
    print('contains_confirm_password', 'confirm_password' in body)

    post = c.post('/reset-password', data={
        'new_password': 'Reset1234',
        'confirm_password': 'Reset1234',
    }, follow_redirects=False)
    print('post_status', post.status_code)
    print('post_location', post.headers.get('Location'))

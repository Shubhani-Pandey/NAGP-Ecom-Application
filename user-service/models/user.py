# models/user.py
from uuid import UUID
from utils.db_utils import DatabasePool, DatabaseError


class UserModel:

    @staticmethod
    def create_user(cognito_user_id, data):
        conn = None
        cursor = None
        try:
            conn = DatabasePool.get_connection('user-service')
            cursor = conn.cursor()
            
            query = """
            INSERT INTO users (cognito_user_id, username, name, email, phone, gender, address, birthdate) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (cognito_user_id, data['username'], data['name'], data['email'], data['phoneNumber'], data['gender'], data['address'], data['birthdate']))
            conn.commit()
            
            return cursor.lastrowid
        except Exception as e:
            raise DatabaseError(f"Error creating user: {str(e)}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    @staticmethod
    def get_user_by_cognito_id(cognito_user_id):
        conn = None
        cursor = None
        try:
            conn = DatabasePool.get_connection('user-service')
            cursor = conn.cursor(dictionary=True)

            print('established cursor conn')
            
            query = "SELECT * FROM users WHERE cognito_user_id = %s"
            cursor.execute(query, (cognito_user_id,))
            result = cursor.fetchone()
            print(result)
            return result
        except Exception as e:
            raise DatabaseError(f"Error fetching user: {str(e)}")
        finally:
            if cursor: 
                cursor.close()
            if conn:
                conn.close()

    @staticmethod
    def update_user(cognito_user_id, update_data):
        conn = None
        cursor = None
        try:
            conn = DatabasePool.get_connection('user-service')
            cursor = conn.cursor()
            
            update_fields = []
            update_values = []
            for key, value in update_data.items():
                if key in ['email', 'name', 'phone']:
                    update_fields.append(f"{key} = %s")
                    update_values.append(value)
            
            if update_fields:
                update_values.append(cognito_user_id)
                query = f"""
                UPDATE users 
                SET {', '.join(update_fields)}
                WHERE cognito_user_id = %s
                """
                cursor.execute(query, update_values)
                conn.commit()
                return True
            return False
        except Exception as e:
            raise DatabaseError(f"Error updating user: {str(e)}")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

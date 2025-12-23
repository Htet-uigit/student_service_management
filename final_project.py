import streamlit as st
import mysql.connector
import pandas as pd
import plotly.express as px
import re

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Student Service Manager", page_icon="🎓", layout="wide")

# --- DATABASE CONNECTION (FIXED FOR HOSTING) ---
def get_db_connection():
    try:
        # Pulls credentials securely from Streamlit Cloud Secrets
        return mysql.connector.connect(
            host=st.secrets["mysql"]["host"],
            user=st.secrets["mysql"]["user"],
            password=st.secrets["mysql"]["password"],
            database=st.secrets["mysql"]["database"],
            port=int(st.secrets["mysql"]["port"]),
            ssl_mode="REQUIRED" # Required for Aiven cloud security
        )
    except mysql.connector.Error as e:
        st.error(f"Error connecting to Cloud MySQL: {e}")
        return None

# --- VALIDATION HELPERS ---
def validate_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email)

def validate_id(sid):
    return re.match(r'^S\d+$', sid)

# --- APP LOGIC ---
def main():
    conn = get_db_connection()
    if not conn: return
    cursor = conn.cursor(dictionary=True)

    st.sidebar.title("🎓 Pro Manager")
    if st.sidebar.button("🔄 Refresh System"):
        st.rerun()
    
    menu = ["📊 Dashboard", "🔍 Search & Manage", "📝 Registration Desk", "📁 Export Reports"]
    choice = st.sidebar.selectbox("Navigation", menu)

    # --- 1. DASHBOARD ---
    if choice == "📊 Dashboard":
        st.title("📊 Institutional Overview")
        df_all = pd.read_sql("SELECT * FROM vw_StudentServiceTracker", conn)
        
        if not df_all.empty:
            col1, col2 = st.columns([1, 1])
            with col1:
                st.subheader("Service Usage Distribution")
                fig_pie = px.pie(df_all, names='Service', title="Usage per Service Category", hole=0.3)
                st.plotly_chart(fig_pie, use_container_width=True)
            with col2:
                st.subheader("Latest Activities")
                st.dataframe(df_all.sort_values(by='Date_Used', ascending=False).head(10), use_container_width=True)
        else:
            st.info("No service data available. Register a student and log an activity first!")

    # --- 2. SEARCH & MANAGE ---
    elif choice == "🔍 Search & Manage":
        st.title("🔍 Search Records")
        st.info("💡 Hint: Type the first letter of a name to see sorted results.")
        search = st.text_input("Search Student Name")
        
        query = "SELECT * FROM vw_StudentServiceTracker"
        if search:
            query += f" WHERE Student LIKE '{search}%' ORDER BY Student ASC"
        
        df = pd.read_sql(query, conn)
        st.dataframe(df, use_container_width=True)

    # --- 3. REGISTRATION & MANAGEMENT ---
    elif choice == "📝 Registration Desk":
        st.title("📝 Student Management")
        
        tab1, tab2, tab3, tab4 = st.tabs(["Add New Student", "Log Service Activity", "Update Email", "🗑️ Remove Records"])
        
        with tab1:
            st.subheader("Enroll a New Student")
            with st.expander("ℹ️ Click for Correct Formats"):
                st.write("- **Student ID**: Must start with 'S' (e.g., S101)")
                st.write("- **Name**: Auto-corrected to Title Case")
                st.write("- **Email**: Standardized to lowercase")

            with st.form("new_student_form", clear_on_submit=True):
                sid = st.text_input("Student ID").strip().upper()
                sname = st.text_input("Full Name").strip().title()
                semail = st.text_input("Email").strip().lower()
                
                if st.form_submit_button("Save Student"):
                    if not validate_id(sid):
                        st.error("❌ ID format error: Must start with 'S'")
                    elif not validate_email(semail):
                        st.error("❌ Invalid Email format.")
                    else:
                        try:
                            cursor.execute("INSERT INTO Students (student_id, name, email) VALUES (%s, %s, %s)", (sid, sname, semail))
                            conn.commit()
                            st.success(f"✅ {sname} added!")
                        except mysql.connector.Error as e:
                            st.error(f"Error: {e}")

        with tab2:
            st.subheader("Log Service Usage")
            st_df = pd.read_sql("SELECT student_id, name FROM Students", conn)
            sv_df = pd.read_sql("SELECT service_id, service_name FROM Services", conn)
            
            with st.form("service_log_form", clear_on_submit=True):
                log_id = st.text_input("Log Entry ID (Format: SS10)").strip().upper()
                selected_st = st.selectbox("Select Student", st_df['name'].tolist())
                selected_sv = st.selectbox("Select Service", sv_df['service_name'].tolist())
                date_val = st.date_input("Service Date")
                
                if st.form_submit_button("Confirm Service Log"):
                    s_id = st_df[st_df['name'] == selected_st]['student_id'].values[0]
                    v_id = sv_df[sv_df['service_name'] == selected_sv]['service_id'].values[0]
                    try:
                        cursor.execute("INSERT INTO StudentServices VALUES (%s, %s, %s, %s)", (log_id, s_id, v_id, date_val))
                        conn.commit()
                        st.success(f"✅ Registered {selected_sv} for {selected_st}")
                    except mysql.connector.Error as e:
                        st.error(f"Error: {e}")

        with tab3:
            st.subheader("Update Student Contact")
            st_list = pd.read_sql("SELECT student_id, name FROM Students", conn)
            target_st = st.selectbox("Select Student to Update", st_list['name'].tolist())
            new_email = st.text_input("New Email Address").strip().lower()
            
            if st.button("Update Email"):
                if validate_email(new_email):
                    tid = st_list[st_list['name'] == target_st]['student_id'].values[0]
                    cursor.execute("UPDATE Students SET email = %s WHERE student_id = %s", (new_email, tid))
                    conn.commit()
                    st.success("✅ Email updated!")

        with tab4:
            st.subheader("🗑️ Remove Student or Specific Service")
            remove_option = st.radio("What would you like to do?", ["Drop a Specific Service", "Delete Entire Student Profile"])
            
            st_list = pd.read_sql("SELECT student_id, name FROM Students", conn)
            
            if remove_option == "Drop a Specific Service":
                st.info("💡 Drop a single service record without deleting the student profile.")
                student_name = st.selectbox("1. Select Student", st_list['name'].tolist())
                
                logs_query = f"""
                    SELECT ss.student_service_id, ser.service_name, ss.service_date 
                    FROM StudentServices ss
                    JOIN Students s ON ss.student_id = s.student_id
                    JOIN Services ser ON ss.service_id = ser.service_id
                    WHERE s.name = '{student_name}'
                """
                logs_df = pd.read_sql(logs_query, conn)
                
                if not logs_df.empty:
                    logs_df['label'] = logs_df['service_name'] + " (" + logs_df['service_date'].astype(str) + ")"
                    selected_log_label = st.selectbox("2. Select Service to Drop", logs_df['label'].tolist())
                    
                    if st.button("Drop Selected Service"):
                        log_id = logs_df[logs_df['label'] == selected_log_label]['student_service_id'].values[0]
                        cursor.execute("DELETE FROM StudentServices WHERE student_service_id = %s", (log_id,))
                        conn.commit()
                        st.success(f"✅ Service '{selected_log_label}' removed for {student_name}.")
                        st.rerun()
                else:
                    st.warning(f"{student_name} is not currently enrolled in any services.")

            else: # Delete Entire Student Profile
                st.error("⚠️ Warning: This will delete the student and ALL their service history.")
                student_to_drop = st.selectbox("1. Select Student Name", st_list['name'].tolist())
                expected_id = st_list[st_list['name'] == student_to_drop]['student_id'].values[0]
                confirm_id = st.text_input(f"2. Type Student ID to confirm ({expected_id})").strip().upper()
                
                if st.button("Confirm Permanent Deletion"):
                    if confirm_id == expected_id:
                        cursor.execute("DELETE FROM Students WHERE student_id = %s", (confirm_id,))
                        conn.commit()
                        st.toast(f"🗑️ Wiped record for {student_to_drop}")
                        st.rerun()
                    else:
                        st.error("❌ Verification Failed: ID does not match.")

    # --- 4. EXPORT ---
    elif choice == "📁 Export Reports":
        st.title("📁 Institutional Reports")
        report = st.radio("Choose View", ["Revenue Report", "Service Tracker"])
        view = "vw_RevenueReport" if report == "Revenue Report" else "vw_StudentServiceTracker"
        df_exp = pd.read_sql(f"SELECT * FROM {view}", conn)
        st.dataframe(df_exp)
        st.download_button(f"📥 Download {report}", df_exp.to_csv(index=False), f"{view}.csv")

    conn.close()

if __name__ == "__main__":
    main()
    

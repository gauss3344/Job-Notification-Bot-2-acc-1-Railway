import requests
import os

def trigger_start():
    # GitHub Secrets থেকে টোকেন নেওয়া
    api_token = os.getenv("RAILWAY_TOKEN")
    
    # আপনার সার্ভিস এবং প্রজেক্ট আইডি (আগের আইডিগুলোই এখানে দেওয়া হয়েছে)
    project_id = "2ce4c16d-0dd9-47b6-b67a-89ecb6963993"
    service_id = "aa713bbd-e18a-4be4-b1b4-f1fd5b9ea624"
    environment_id = "1a47c532-de5a-438a-813e-24ae07654e6e"

    url = "https://backboard.railway.app/graphql/v2"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    # নতুন Redeploy কুয়েরি
    query = """
    mutation serviceInstanceRedeploy($environmentId: String!, $serviceId: String!) {
      serviceInstanceRedeploy(environmentId: $environmentId, serviceId: $serviceId)
    }
    """
    
    variables = {
        "environmentId": environment_id,
        "serviceId": service_id
    }
    
    try:
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
        data = response.json()

        if response.status_code == 200 and "errors" not in data:
            print("✅ Railway Service Redeploy Triggered Successfully!")
        else:
            error_msg = data.get("errors", [{"message": "Unknown error"}])[0].get("message")
            print(f"❌ Failed to Redeploy: {error_msg}")
            
    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    trigger_start()

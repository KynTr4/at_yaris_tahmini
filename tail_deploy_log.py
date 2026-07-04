from vps_ssh import connect_vps

def main():
    ssh = connect_vps()
    
    try:
        stdin, stdout, stderr = ssh.exec_command("tail -n 30 /tmp/deploy.log || echo 'no log yet'")
        print("DEPLOY LOG TAIL:")
        print(stdout.read().decode('utf-8'))
        
        stdin, stdout, stderr = ssh.exec_command("ps aux | grep -E 'deploy|rsync' | grep -v grep || echo 'no process'")
        print("RUNNING DEPLOY PROCESSES:")
        print(stdout.read().decode('utf-8'))
    finally:
        ssh.close()

if __name__ == '__main__':
    main()

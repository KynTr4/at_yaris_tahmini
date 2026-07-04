from vps_ssh import connect_vps

def main():
    ssh = connect_vps()
    
    try:
        # Delete the previous failed/old deployment backups to free up space
        print("Cleaning up old deploy backups...")
        stdin, stdout, stderr = ssh.exec_command("rm -rf /var/backups/at_yaris_tahmini/deploy_backup_*")
        print(stdout.read().decode('utf-8'))
        print(stderr.read().decode('utf-8'))
        
        stdin, stdout, stderr = ssh.exec_command("df -h")
        print("DF AFTER CLEANUP:")
        print(stdout.read().decode('utf-8'))
    finally:
        ssh.close()

if __name__ == '__main__':
    main()

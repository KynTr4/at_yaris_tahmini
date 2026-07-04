from vps_ssh import connect_vps

def main():
    ssh = connect_vps()
    
    try:
        stdin, stdout, stderr = ssh.exec_command("stat /opt/at_yaris_tahmini/pedigreeall_progress.db")
        print("STAT OUTPUT:")
        print(stdout.read().decode('utf-8'))
        print(stderr.read().decode('utf-8'))
    finally:
        ssh.close()

if __name__ == '__main__':
    main()

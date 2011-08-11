#include "misc.h"
#include "deht.h"
#include "iniloader.h"
#include "rainbow.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _MSC_VER
	#define strcasecmp _stricmp
#else
	#include <strings.h>
#endif


static int get_params_from_ini(const inifile_t * ini, int * chain_length, int * multi_query,
							   int * digest_size, BasicHashFunctionPtr * hashfunc)
{
	const char * hashname;

	if (ini_get_integer(ini, "num_of_R", chain_length) != INI_STATUS_OK) {
		fprintf(stderr, "INI file did not specify 'num_of_R'\n");
		return 1;
	}
	if (ini_get_integer(ini, "multi_query", multi_query) != INI_STATUS_OK) {
		fprintf(stderr, "INI file did not specify 'multi_query'\n");
		return 1;
	}
	hashname = ini_get(ini, "hash_name");
	if (hashname == NULL) {
		fprintf(stderr, "INI file did not specify 'hash_name'\n");
		return 1;
	}
	if (strcasecmp(hashname, "MD5") == 0) {
		*hashfunc = MD5BasicHash;
		*digest_size = MD5_OUTPUT_LENGTH_IN_BYTES;
	}
	else if (strcasecmp(hashname, "SHA1") == 0) {
		*hashfunc = SHA1BasicHash;
		*digest_size = SHA1_OUTPUT_LENGTH_IN_BYTES;
	}
	else {
		fprintf(stderr, "Invalid hash_name: '%s'\n", hashname);
		return 1;
	}

	return 0;
}

static int user_input_loop(DEHT * deht, const uint64_t * seed_table,
							BasicHashFunctionPtr hashfunc, int digest_size,
							int chain_length, int multi_query)
{
	char line[MAX_INPUT_BUFFER];
	unsigned char digest[MAX_DIGEST_LENGTH_IN_BYTES];
	char hexdigest[MAX_DIGEST_LENGTH_IN_BYTES * 2 + 1];
	char * cmd, * rcmd;

	while (1) {
		printf(">> ");
		if (fgets(line, sizeof(line)-1, stdin) == NULL) {
			break;
		}
		/* trim whitespace */
		for (cmd = line; *cmd == ' ' || *cmd == '\t'; cmd++);
		for (rcmd = cmd + strlen(cmd) - 1; *rcmd == ' ' || *rcmd == '\t' || *rcmd == '\n'; rcmd--) {
			*rcmd = '\0';
		}
		if (*cmd == '\0') {
			continue; /* empty line */
		}
		else if (strcasecmp(cmd, "quit") == 0) {
			break; /* quit cleanly */
		}

		if (cmd[0] == '!') {
			/* plain-text password */
			cmd++;
			hashfunc((unsigned char*)cmd, strlen(cmd), digest);
			binary2hexa(digest, digest_size, hexdigest, sizeof(hexdigest));
			printf("\tIn hexa password is %s\n", hexdigest);
		}
		else if (hexa2binary(cmd, digest, digest_size) < 0) {
			if (strlen(cmd) > (unsigned)digest_size) {
				fprintf(stderr, "Too long\n");
			}
			else {
				fprintf(stderr, "Non hexa\n");
			}
			continue;
		}

		/*if (rainbow_query(deht, rule, seed_table, chain_length, multi_query, digest) != 0) {
			return 1;
		}*/
	}

	return 0;
}


int main(int argc, const char ** argv)
{
	int res = 1;
	inifile_t ini;
	DEHT * deht = NULL;
	uint64_t * seed_table = NULL;
	char inifilename[MAX_INPUT_BUFFER];

	int chain_length;
	int multi_query;
	int digest_size;
	BasicHashFunctionPtr hashfunc = NULL;

	if (argc != 2) {
		fprintf(stderr, "Usage: %s <prefix>\n", argv[0]);
		return 1;
	}

	/* load ini */
	strncpy(inifilename, argv[1], sizeof(inifilename) - 5);
	strcat(inifilename, ".ini");
	if (ini_load(&ini, inifilename) != INI_STATUS_OK) {
		/* error message printed by ini_load */
		goto cleanup0;
	}

	/* load DEHT */
	deht = load_DEHT_from_files(argv[1], my_hash_func, my_valid_func);
	if (deht == NULL) {
		/* error message printed by load_DEHT */
		goto cleanup1;
	}
	if (read_DEHT_pointers_table(deht) != DEHT_STATUS_SUCCESS) {
		/* error message printed by read_DEHT_pointers_table */
		goto cleanup1;
	}

	/* read params */
	if (get_params_from_ini(&ini, &chain_length, &multi_query, &digest_size,
			&hashfunc) != 0) {
		/* error message printed by get_params_from_ini */
		goto cleanup2;
	}

	/* load seed table */
	seed_table = rainbow_load_seed_table(argv[1], chain_length);
	if (seed_table == NULL) {
		/* error message printed by load_seed_table */
		goto cleanup2;
	}

	/* main loop */
	res = user_input_loop(deht, seed_table, hashfunc, digest_size, chain_length,
		multi_query);

	free(seed_table);
cleanup2:
	close_DEHT_files(deht);
cleanup1:
	ini_finalize(&ini);
cleanup0:
	return res;
}


